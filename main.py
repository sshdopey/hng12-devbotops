import os
import threading
from datetime import datetime

import requests

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import Config, logger
from server.aws import setup_aws_instance
from spreadsheet import Sheet
from stages.stage_0 import StageZero
from stages.stage_1 import StageOne
from stages.stage_2 import StageTwo
from stages.stage_2_backend import StageTwoBackend
from utils import get_stage

app = App(
    token=Config.SLACK_BOT_TOKEN, signing_secret=Config.SLACK_SIGNING_SECRET
)

stages = {0: StageZero, 1: StageOne, 2: StageTwo, 2.5: StageTwoBackend}


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


@app.command("/request-server")
def handle_server_request(ack, body, client):
    """Handle server request command"""
    try:
        sheet = Sheet(
            "1b9zb83mMZXoJn3B191oQru3_ZHq2COxqmbYtbH0xhuo",
            {
                "A": "timestamp",
                "B": "display_name",
                "C": "user_id",
                "D": "instance_id",
                "E": "key_id",
                "F": "ip_address",
                "G": "status",
            },
        )
        ack()

        existing_request = sheet.get_row("user_id", body["user_id"])
        if existing_request:
            _, row_data = existing_request
            if row_data["status"] == "provisioning":
                client.chat_postEphemeral(
                    channel=body["channel_id"],
                    user=body["user_id"],
                    text="⚠️ You already have a server being provisioned. Please wait for it to complete.",
                )
                return
            client.chat_postEphemeral(
                channel=body["channel_id"],
                user=body["user_id"],
                text="⚠️ You have already been provided a server. Multiple server requests are not allowed.",
            )
            return

        sheet.append(
            {
                "timestamp": datetime.now().strftime("%m/%d/%Y %H:%M:%S"),
                "display_name": body["user_name"],
                "user_id": body["user_id"],
                "status": "provisioning",
            }
        )

        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text="🔄 Your server is being provisioned. This may take a few minutes...",
        )

        def provision_server():
            try:
                instance_data = setup_aws_instance()

                row_index, _ = sheet.get_row("user_id", body["user_id"])
                sheet.update(
                    row_index,
                    {
                        "instance_id": instance_data["instance_id"],
                        "key_id": instance_data["key_id"],
                        "ip_address": instance_data["ip_address"],
                        "status": "ready",
                    },
                )

                # First open DM conversation
                dm_response = client.conversations_open(
                    users=[body["user_id"]]
                )
                if not dm_response["ok"]:
                    raise Exception("Failed to open DM channel")

                dm_channel_id = dm_response["channel"]["id"]

                # Get upload URL from Slack
                key_file_path = instance_data["key_path"]
                key_file_size = os.path.getsize(key_file_path)
                response = client.files_getUploadURLExternal(
                    filename=instance_data["key_id"] + ".pem",
                    length=key_file_size,
                )
                upload_url = response["upload_url"]
                file_id = response["file_id"]

                # Upload file to URL
                with open(instance_data["key_path"], "rb") as f:
                    requests.put(upload_url, data=f)
                    # Complete upload and share in DM
                    client.files_completeUploadExternal(
                        files=[
                            {
                                "id": file_id,
                                "title": instance_data["key_id"] + ".pem",
                            }
                        ],
                        channel_id=dm_channel_id,  # Use DM channel ID here
                    )

                    # Share file publicly and get URL
                    file_share = client.files_sharedPublicURL(file=file_id)
                    public_url = file_share["file"]["permalink_public"]

                    client.chat_postMessage(
                        channel=dm_channel_id,  # Use DM channel ID here
                        text=f"✅ Server has been provisioned successfully!\n"
                        f"Instance ID: {instance_data['instance_id']}\n"
                        f"IP Address: {instance_data['ip_address']}\n"
                        f"Username: {instance_data['username']}\n"
                        f"SSH Key Download Link: {public_url}\n",
                    )
                logger.info("server provisioned")

            except Exception as e:
                logger.error(f"Error in server provisioning: {str(e)}")
                client.chat_postMessage(
                    channel=body["user_id"],
                    text="❌ Server provisioning failed. Please try again.",
                )

        thread = threading.Thread(target=provision_server)
        thread.start()

    except Exception as e:
        logger.error(f"Error handling server request: {str(e)}")
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text="🔧 Oops! Something went wrong setting up the server. Please try again.",
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
