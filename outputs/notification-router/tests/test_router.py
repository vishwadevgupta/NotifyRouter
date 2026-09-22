import unittest

from app.models import Action, MessageType, Media, RouteRequest, SenderContext, UserContext
from app.router import NotificationRouter


class NotificationRouterTest(unittest.TestCase):
    def test_otp_is_never_notified(self):
        r = RouteRequest(message_id="1", text="Please share your OTP now", conversation_type="personal")
        self.assertEqual(NotificationRouter().route(r).action, Action.mute)

    def test_trusted_deadline_notifies(self):
        r = RouteRequest(
            message_id="2",
            text="Payment due today",
            conversation_type="business",
            sender=SenderContext(trusted=True, verified_business=True, domain_matches=True),
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.notify)

    def test_urgent_bill_notification_notifies(self):
        r = RouteRequest(
            message_id="11",
            text="please pay the electricity bill now otherwise connection will be lost immediately",
            conversation_type="personal",
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.notify)
        self.assertEqual(NotificationRouter().route(r).message_type, MessageType.payment)

    def test_importance_layer_preserves_digest_without_llm(self):
        r = RouteRequest(
            message_id="3",
            text="This is a casual note that can wait.",
            conversation_type="personal",
            user=UserContext(quiet_hours=True),
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.digest)

    def test_event_in_quiet_hours_is_digested(self):
        r = RouteRequest(
            message_id="4",
            text="Society meeting notice for tomorrow.",
            conversation_type="group",
            user=UserContext(quiet_hours=True),
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.digest)

    def test_promotion_opt_out_mutes_promos(self):
        r = RouteRequest(
            message_id="5",
            text="Big sale: 50% off everything this weekend!",
            conversation_type="personal",
            user=UserContext(promotions_opted_out=True),
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.mute)

    def test_call_me_triggers_urgent(self):
        r = RouteRequest(
            message_id="7",
            text="Please call me",
            conversation_type="personal",
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.notify)
        self.assertEqual(NotificationRouter().route(r).message_type, MessageType.urgent)

    def test_accident_message_triggers_urgent(self):
        r = RouteRequest(
            message_id="8",
            text="I met with an accident",
            conversation_type="personal",
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.notify)
        self.assertEqual(NotificationRouter().route(r).message_type, MessageType.urgent)

    def test_voice_media_with_transcript_is_evaluated(self):
        r = RouteRequest(
            message_id="9",
            text="",
            conversation_type="personal",
            media=Media(kind="voice", transcript="Please call me immediately", audio_data_url="https://example.com/voice.mp3"),
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.notify)

    def test_image_media_does_not_break_route(self):
        r = RouteRequest(
            message_id="10",
            text="Just sharing an image",
            conversation_type="personal",
            media=Media(kind="image", image_data_url="https://example.com/photo.jpg"),
        )
        self.assertIn(NotificationRouter().route(r).action, {Action.digest, Action.notify, Action.mute})

    def test_muted_group_without_mention_mutes(self):
        r = RouteRequest(
            message_id="6",
            text="Who wants to join for a group chat later?",
            conversation_type="group",
            user=UserContext(group_muted=True, direct_mention=False),
        )
        self.assertEqual(NotificationRouter().route(r).action, Action.mute)


if __name__ == "__main__":
    unittest.main()
