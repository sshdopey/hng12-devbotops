from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import Config, logger
from stage_zero import StageZeroHandler

app = App(
    token=Config.SLACK_BOT_TOKEN, signing_secret=Config.SLACK_SIGNING_SECRET
)

STAGE_HANDLERS = {
    0: StageZeroHandler,
    # Add more stage handlers later
}


@app.event("message")
def handle_message(event, client):
    """Handle message events"""
    if app.client.auth_test()["user_id"] in event.get("text", ""):
        client.chat_postMessage(
            channel=event["channel"],
            thread_ts=event.get("ts"),
            text="Please use */submit* to submit your task.",
        )


@app.command("/submit")
def handle_submit(ack, body, client):
    """Handle the /submit command"""
    try:
        ack()

        stage = Config.get_stage_for_channel(body["channel_id"])
        if stage is None:
            client.chat_postEphemeral(
                channel=body["channel_id"],
                user=body["user_id"],
                text="Wrong channel! 🙈 Head to the right devops stage channel to submit!",
            )
            return

        handler = STAGE_HANDLERS.get(stage)
        if not handler:
            client.chat_postEphemeral(
                channel=body["channel_id"],
                user=body["user_id"],
                text="I'm not ready to grade this stage! 🏗️ Check back later ☕",
            )
            return

        view = handler.create_modal_view(
            body["trigger_id"], body["channel_id"]
        )
        client.views_open(trigger_id=body["trigger_id"], view=view)

    except Exception as e:
        logger.error(f"Error handling submit command: {str(e)}")
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text="🔧 Oops! Something went wrong. Please try again.",
        )


@app.view("submission")
def handle_submission(ack, body, client):
    """Handle submission"""
    try:
        ack()
        user_id = body["user"]["id"]
        channel_id, stage = body["view"]["private_metadata"].split(":")
        stage = int(stage)
        handler = STAGE_HANDLERS.get(stage)
        handler.handle_submission(user_id, channel_id, body, client)
    except Exception as e:
        logger.error(f"Error handling submission: {str(e)}")
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="🔧 Oops! Something went wrong. Please try again.",
        )


def main():
    """Main entry point"""
    try:
        handler = SocketModeHandler(app, Config.SLACK_APP_TOKEN)
        handler.start()
    except Exception as e:
        logger.critical(f"Application failed to start: {str(e)}")
        raise


if __name__ == "__main__":
    main()
