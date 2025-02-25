import asyncio
import json
from datetime import UTC, datetime, timedelta
from multiprocessing import AuthenticationError
from typing import Literal, NoReturn

import httpx
import jwt

from ..db.base_repo import BaseRepository
from ..models.sbat import (
    EXAM_CENTER_MAP,
    ExamTimeSlotCreate,
    ExamTimeSlotRead,
    MonitorConfiguration,
    MonitorStatus,
    SbatRequestCreate,
    SbatRequestRead,
)
from ..models.settings import Settings
from ..utils import (
    send_discord_message_with_role_mention,
    send_email,
    send_telegram_message_to_all,
)


class SbatMonitor:

    AUTH_URL = "https://api.rijbewijs.sbat.be/praktijk/api/user/authenticate"
    CHECK_URL = "https://api.rijbewijs.sbat.be/praktijk/api/exam/available"
    STANDARD_HEADERS: dict[str, str] = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "User-Agent": "PostmanRuntime/7.39.1",
        "Accept-Encoding": "gzip, deflate, br",
    }

    def __init__(
        self, repo: BaseRepository, settings: Settings, config: MonitorConfiguration
    ) -> None:
        self.repo: BaseRepository = repo
        self.settings: Settings = settings

        # Initialize with default values to ensure consistency
        self.license_types: list[Literal["B", "AM"]] = ["B"]
        self.exam_center_ids: list[int] = [1]
        self.seconds_inbetween: int = 300

        self.config = config

        self.task: asyncio.Task | None = None
        self.total_time_running: timedelta = timedelta()
        self.first_started_at: datetime | None = None
        self.last_started_at: datetime | None = None
        self.last_stopped_at: datetime | None = None
        self.stopped_due_to: str | None = None

    @property
    def config(self) -> MonitorConfiguration:
        return self._config

    @config.setter
    def config(self, new_config) -> None:
        if not isinstance(new_config, MonitorConfiguration):
            raise TypeError(
                "Expected new_config to be an instance of MonitorConfiguration"
            )

        self._config: MonitorConfiguration = new_config
        self.license_types: list[Literal["B", "AM"]] = new_config.license_types
        self.exam_center_ids: list[int] = new_config.exam_center_ids
        self.seconds_inbetween: int = new_config.seconds_inbetween

    async def start(self) -> None:
        if self.task:
            raise RuntimeError("Monitoring is already running.")
        self.task = asyncio.create_task(self.check_for_time_slots())
        self.last_started_at: datetime = datetime.now()
        self.first_started_at: datetime = self.first_started_at or self.last_started_at
        self.task.add_done_callback(self.clean_up)

    async def stop(self) -> None:
        if not self.task or self.task.done():
            raise RuntimeError("Monitoring is not running.")
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass

    def clean_up(self, task: asyncio.Task) -> None:
        if task.cancelled():
            self.stopped_due_to = "SBAT MONITOR STOPPED: Task was cancelled."
        elif task.done():
            exception: BaseException | None = task.exception()
            if exception:
                self.stopped_due_to = (
                    f"SBAT MONITOR STOPPED: Exception occurred: {exception}"
                )
            else:
                self.stopped_due_to = (
                    "SBAT MONITOR STOPPED: Task completed successfully."
                )

        self.last_stopped_at = datetime.now()
        if self.last_started_at:
            self.total_time_running += self.last_stopped_at - self.last_started_at
        self.task = None

    def status(self) -> MonitorStatus:
        if self.task and not self.task.done():
            current_time: datetime = datetime.now()
            running_time: timedelta = (
                (current_time - self.last_started_at)
                if self.last_started_at
                else timedelta()
            )
            total_time_running: timedelta = self.total_time_running + running_time
        else:
            total_time_running: timedelta = self.total_time_running

        return MonitorStatus(
            running=self.task is not None and not self.task.done(),
            seconds_inbetween=self.seconds_inbetween,
            license_types=self.license_types,
            exam_centers=[EXAM_CENTER_MAP[c_id] for c_id in self.exam_center_ids],
            task_done=self.task.done() if self.task else None,
            total_time_running=str(total_time_running),
            first_started_at=self.first_started_at,
            last_started_at=self.last_started_at,
            last_stopped_at=self.last_stopped_at,
            stopped_due_to=self.stopped_due_to,
        )

    async def authenticate(self) -> str:
        last_request: SbatRequestRead | None = (
            await self.repo.find_last_sbat_auth_request()
        )
        if last_request:
            try:
                payload: dict = jwt.decode(
                    last_request.response.get("response_text"),
                    options={"verify_signature": False},
                )
                if datetime.now() < datetime.fromtimestamp(payload["exp"]):
                    return last_request.response.get("response_text")
            except (jwt.DecodeError, jwt.InvalidTokenError, jwt.ExpiredSignatureError):
                pass

        async with httpx.AsyncClient() as client:
            auth_response: httpx.Response = await client.post(
                self.AUTH_URL,
                json={
                    "username": self.settings.sbat_username,
                    "password": self.settings.sbat_password,
                },
                headers=self.STANDARD_HEADERS,
                timeout=60,
            )

        sbat_request = SbatRequestCreate(
            timestamp=datetime.now(UTC),
            request_type="authentication",
            response={
                "status_code": auth_response.status_code,
                "headers": auth_response.headers,
                "response_text": auth_response.text,
            },
            url=self.AUTH_URL,
            email_used=self.settings.sbat_username,
        )
        await self.repo.create("requests", sbat_request, SbatRequestRead)

        if auth_response.status_code == 200:
            token: str = auth_response.text
            return token
        else:
            raise AuthenticationError("Authentication failed")

    async def check_for_time_slots(self) -> NoReturn:
        token: str = await self.authenticate()
        headers: dict[str, str] = {
            **self.STANDARD_HEADERS,
            "Authorization": f"Bearer {token}",
        }

        while True:
            for license_type in self.license_types:
                for exam_center_id in self.exam_center_ids:
                    exam_center_name: str = EXAM_CENTER_MAP[exam_center_id]
                    response, request_body = await self._perform_check(
                        headers, license_type, exam_center_id, exam_center_name
                    )

                    # possible exp of token
                    if self._is_exp_error(response):
                        headers: dict[str, str] = {
                            **self.STANDARD_HEADERS,
                            "Authorization": f"Bearer {await self.authenticate()}",
                        }
                        continue

                    await self._handle_response(response, request_body)
                    await asyncio.sleep(self.seconds_inbetween)

    async def _perform_check(
        self,
        headers: dict[str, str],
        license_type: str,
        exam_center_id: int,
        exam_center_name: str,
    ) -> tuple[httpx.Response, dict]:
        print(
            f"Checking '{exam_center_name}' for new time slots for license type '{license_type}'..."
        )
        async with httpx.AsyncClient() as client:
            body: dict = {
                "examCenterId": exam_center_id,
                "licenseType": license_type,
                "examType": "E2",
                "startDate": datetime.combine(
                    datetime.now().date(), datetime.min.time()
                ).isoformat(),
            }
            return (
                await client.post(
                    self.CHECK_URL,
                    headers=headers,
                    json=body,
                    timeout=60,
                ),
                body,
            )

    def _is_exp_error(self, response: httpx.Response) -> bool:
        www_authenticate: str | None = response.headers.get("WWW-Authenticate")
        return (
            response.status_code == 401
            and www_authenticate
            and "expired" in www_authenticate.lower()
        )

    async def _handle_response(
        self, response: httpx.Response, request_body: dict
    ) -> None:
        license_type: str = request_body.get("licenseType")
        exam_center_id: int = request_body.get("examCenterId")
        exam_center_name: str = EXAM_CENTER_MAP[exam_center_id]
        if response.status_code == 200:
            data: dict = response.json()
            await self.notify_users_and_update_db(
                data, exam_center_id, exam_center_name, license_type
            )

        else:
            sbat_request = SbatRequestCreate(
                timestamp=datetime.now(UTC),
                request_type="check_for_time_slots",
                request_body=request_body,
                response={
                    "status_code": response.status_code,
                    "headers": response.headers,
                    "response_text": response.text,
                },
                url=self.CHECK_URL,
                email_used=self.settings.sbat_username,
            )
            await self.repo.create("requests", sbat_request, SbatRequestRead)

    async def notify_users_and_update_db(
        self,
        time_slots: list[dict],
        exam_center_id: int,
        exam_center_name: str,
        license_type: str,
    ) -> None:
        current_time_slots = set()
        notified_time_slots: set[int] = await self.repo.find_notified_time_slot_ids(
            exam_center_id, license_type
        )
        message: str = ""

        for time_slot in time_slots:
            exam_id: int = time_slot["id"]
            start_time: datetime = datetime.fromisoformat(time_slot["from"])
            end_time: datetime = datetime.fromisoformat(time_slot["till"])
            current_time_slots.add(exam_id)

            if exam_id not in notified_time_slots:

                new_time_slot_messag: str = (
                    f"{start_time.date()}  {start_time.time()} - {end_time.time()}\n"
                )
                if new_time_slot_messag not in message:
                    message += new_time_slot_messag

                found_slot: ExamTimeSlotRead | None = await self.repo.find_one(
                    "slots", {"exam_id": exam_id}, ExamTimeSlotRead
                )
                if found_slot and found_slot.status == "taken":
                    await self.repo.update_time_slot_status(exam_id, "notified")
                else:
                    time_slot_to_add = ExamTimeSlotCreate(
                        exam_id=time_slot["id"],
                        first_found_at=datetime.now(UTC),
                        found_at=datetime.now(UTC),
                        start_time=datetime.fromisoformat(time_slot["from"]),
                        end_time=datetime.fromisoformat(time_slot["till"]),
                        status="notified",
                        is_public=time_slot["isPublic"],
                        day_id=time_slot["dayScheduleId"],
                        driving_school=time_slot["drivingSchool"],
                        exam_center_id=time_slot["examCenterId"],
                        exam_type=time_slot["examType"],
                        examinee=time_slot["examinee"],
                        types_blob=json.loads(time_slot["typesBlob"]),
                    )
                    await self.repo.create("slots", time_slot_to_add, ExamTimeSlotRead)

        if message:
            subject: str = (
                f"New driving exam time slots available for license type '{license_type}' at exam center '{exam_center_name}':"
            )
            message: str = (
                subject
                + "\nLink: https://rijbewijs.sbat.be/praktijk/examen/Login \n"
                + message
            )
            email_recipients: set[str] = await self.repo.find_all_subscribed_emails(
                exam_center_id, license_type
            )
            telegram_recipients: set[int] = (
                await self.repo.find_all_subscribed_telegram_ids(
                    exam_center_id, license_type
                )
            )
            send_email(
                subject,
                email_recipients,
                self.settings.sender_email,
                self.settings.sender_password,
                self.settings.smtp_server,
                self.settings.smtp_port,
                message=message,
            )
            await send_discord_message_with_role_mention(
                self.settings.discord_bot_token,
                self.settings.discord_guild_id,
                self.settings.discord_channel_id,
                f"{exam_center_name} - {license_type}",
                message,
            )
            await send_telegram_message_to_all(
                message, self.settings.telegram_bot_token, telegram_recipients
            )

        for exam_id in notified_time_slots - current_time_slots:
            await self.repo.update_time_slot_status(exam_id, "taken")
            await self.repo.update_one(
                "slots",
                {"exam_id": exam_id, "first_taken_at": None},
                {"first_taken_at": datetime.now(UTC)},
                ExamTimeSlotRead,
            )
