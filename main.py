from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import Config, logger
from stages.stage_0 import StageZero
from stages.stage_1 import StageOne
from utils import get_stage

app = App(
    token=Config.SLACK_BOT_TOKEN, signing_secret=Config.SLACK_SIGNING_SECRET
)

stages = {0: StageZero, 1: StageOne}


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
        channel_id = body["channel_id"]
        trigger_id = body["trigger_id"]
        stage = get_stage(stages, channel_id)
        if stage is None:
            client.views_open(
                trigger_id=trigger_id,
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Channel Error"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"The */submit* command cannot be used in <#{body['channel_id']}> 🙈.\nPlease head to the right devops stage channel to submit!",
                            },
                        }
                    ],
                },
            )
            return

        client.views_open(
            trigger_id=trigger_id, view=stage.submission_view(channel_id)
        )

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
        channel = body["view"]["private_metadata"]
        stage = get_stage(stages, channel)
        stage.submit(channel, body, client)
    except Exception as e:
        logger.error(f"Error handling submission: {str(e)}")
        client.chat_postEphemeral(
            channel=channel,
            user=channel,
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
