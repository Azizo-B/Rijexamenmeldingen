from ..db.base_repo import BaseRepository
from ..models.discord import DiscordSubscriptionRoles
from ..models.settings import Settings
from ..models.subscriber import SubscriberRead
from ..utils import is_user_in_guild, remove_role_from_user, send_email


async def handle_invoice_payment_failed(repo: BaseRepository, settings: Settings, invoice: dict) -> None:
    cus: str | None = invoice.get("customer")
    subscriber: SubscriberRead | None = await repo.find_one("subscribers", {"stripe_customer_id": cus}, SubscriberRead)
    if subscriber:
        send_email(
            "Betalingsfout - Actie Vereist",
            [subscriber.email],
            settings.sender_email,
            settings.sender_password,
            settings.smtp_server,
            settings.smtp_port,
            is_html=True,
            html_template="payment_failed_email.html",
            naam=subscriber.name,
        )


async def handle_invoice_payment_succeeded(repo: BaseRepository, invoice: dict) -> SubscriberRead | None:
    return await repo.activate_subscriber_subscription(invoice.get("customer"), invoice.get("amount_paid"))


async def handle_subscription_deleted(repo: BaseRepository, settings: Settings, subscription: dict) -> None:
    cus: str | None = subscription.get("customer")
    subscriber: SubscriberRead | None = await repo.update_one(
        "subscribers", {"stripe_customer_id": cus}, {"is_subscription_active": False}, SubscriberRead
    )
    discord_user_id = subscriber.discord_user.get("id")
    if await is_user_in_guild(settings.discord_guild_id, discord_user_id, settings.discord_bot_token):
        await remove_role_from_user(
            settings.discord_guild_id, discord_user_id, DiscordSubscriptionRoles.ACTIVE.value, settings.discord_bot_token
        )
    if subscriber:
        send_email(
            "Bevestiging van Annulering van je Abonnement.",
            [subscriber.email],
            settings.sender_email,
            settings.sender_password,
            settings.smtp_server,
            settings.smtp_port,
            is_html=True,
            html_template="cancellation_email.html",
            naam=subscriber.name,
        )


async def handle_checkout_session_completed(repo: BaseRepository, settings: Settings, session: dict) -> None:
    subscriber: SubscriberRead = await repo.process_checkout_session(session)
    send_email(
        "Betaling geslaagd!",
        [subscriber.email],
        settings.sender_email,
        settings.sender_password,
        settings.smtp_server,
        settings.smtp_port,
        is_html=True,
        html_template="confirmation_email.html",
        naam=subscriber.name,
        telegram_link="https://t.me/+irHB91aMk1Q0MGNk",
        discord_link="https://discord.gg/fhA5c4tTww",
    )
