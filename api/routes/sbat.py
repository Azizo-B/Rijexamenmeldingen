import asyncio

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.db import mongoDB
from api.models import MonitorStatus

from ..dependencies import get_admin_user, get_db, get_sbat_monitor
from ..models import ExamTimeSlotRead, MonitorConfiguration, SbatRequestRead
from ..services.sbat_monitor import SbatMonitor

router = APIRouter(dependencies=[Depends(get_admin_user)])


@router.post("/startup", tags=["SBAT monitor"])
async def start_monitoring(config: MonitorConfiguration, sbat_monitor: SbatMonitor = Depends(get_sbat_monitor)) -> dict[str, str]:
    sbat_monitor.config = config
    await sbat_monitor.start()
    await asyncio.sleep(3)
    return sbat_monitor.status()


@router.post("/monitor-config", tags=["SBAT monitor"])
def update_monitoring_configurations(config: MonitorConfiguration, sbat_monitor: SbatMonitor = Depends(get_sbat_monitor)) -> MonitorStatus:
    sbat_monitor.config = config
    return sbat_monitor.status()


@router.get("/monitor-status", tags=["SBAT monitor"])
def get_monitoring_status(sbat_monitor: SbatMonitor = Depends(get_sbat_monitor)) -> MonitorStatus:
    return sbat_monitor.status()


@router.get("/shutdown", tags=["SBAT monitor"])
async def stop_monitoring(sbat_monitor: SbatMonitor = Depends(get_sbat_monitor)) -> dict[str, str]:
    try:
        await sbat_monitor.stop()
        return {"status": "Stopped successfully"}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"status": f"Failed to stop monitoring: {str(e)}"}


@router.get("/requests", tags=["SBAT monitor"])
async def get_requests(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[SbatRequestRead]:
    return await mongoDB.get_requests(db)


@router.get("/exam-time-slots", tags=["SBAT monitor"])
async def get_exam_time_slots(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[ExamTimeSlotRead]:
    return await mongoDB.get_time_slots(db)