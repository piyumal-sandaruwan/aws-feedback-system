
import json
import os
import uuid
import base64
import binascii
import html
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


# Read your existing Lambda environment variables
TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET_NAME = os.environ["BUCKET_NAME"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
REGION = os.environ.get("REGION") or os.environ["AWS_REGION"]

MAX_PDF_BYTES = 4 * 1024 * 1024  # 4 MB

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
ses = boto3.client("ses", region_name=REGION)


def make_response(status_code, message, feedback_id=None):
    result = {"message": message}

    if feedback_id:
        result["feedback_id"] = feedback_id

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(result),
    }


def build_email(name, email, message, file_url):
    safe_name = html.escape(name)
    safe_email = html.escape(email)
    safe_message = html.escape(message).replace("\n", "<br>")

    attachment_html = ""

    if file_url:
        safe_url = html.escape(file_url, quote=True)
        attachment_html = f"""
        <tr>
            <td><strong>Attachment</strong></td>
            <td>
                <a href="{safe_url}">View PDF Attachment</a>
                <p>This link expires after 24 hours.</p>
            </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;background:#f1f5f9;padding:20px;">
        <div style="max-width:600px;margin:auto;background:#ffffff;padding:25px;
                    border-radius:10px;">
            <h2 style="color:#1d4ed8;">New Feedback Received</h2>
            <table style="width:100%;border-collapse:collapse;">
                <tr>
                    <td><strong>Name</strong></td>
                    <td>{safe_name}</td>
                </tr>
                <tr>
                    <td><strong>Email</strong></td>
                    <td>{safe_email}</td>
                </tr>
                <tr>
                    <td><strong>Message</strong></td>
                    <td>{safe_message}</td>
                </tr>
                {attachment_html}
            </table>
            <p style="color:#64748b;font-size:12px;">
                Automatically sent by your feedback application.
            </p>
        </div>
    </body>
    </html>
    """


def lambda_handler(event, context):
    method = event.get("httpMethod")

    if not method:
        method = (
            event.get("requestContext", {})
            .get("http", {})
            .get("method")
        )

    if method == "OPTIONS":
        return make_response(200, "CORS preflight successful")

    try:
        raw_body = event.get("body")

        if raw_body is None:
            body = event
        else:
            if event.get("isBase64Encoded"):
                raw_body = base64.b64decode(raw_body).decode("utf-8")

            body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body

        if not isinstance(body, dict):
            return make_response(400, "Invalid request body.")

        name = body.get("name")
        email = body.get("email")
        message = body.get("message")
        file_base64 = body.get("file_base64")

        if not all(
            isinstance(value, str) and value.strip()
            for value in (name, email, message)
        ):
            return make_response(
                400, "Name, email and message are required."
            )

        name = name.strip()
        email = email.strip()
        message = message.strip()

        if len(name) > 200 or len(email) > 254 or len(message) > 10000:
            return make_response(400, "One or more fields are too long.")

        if "@" not in email:
            return make_response(400, "Please provide a valid email address.")

        feedback_id = str(uuid.uuid4())
        file_url = None

        # Optional PDF attachment
        if file_base64:
            if not isinstance(file_base64, str):
                return make_response(400, "Invalid PDF attachment.")

            try:
                encoded_data = file_base64.split(",", 1)[-1]
                pdf_data = base64.b64decode(encoded_data, validate=True)
            except (binascii.Error, ValueError):
                return make_response(400, "Invalid PDF encoding.")

            if len(pdf_data) > MAX_PDF_BYTES:
                return make_response(400, "PDF must be 4 MB or smaller.")

            if not pdf_data.startswith(b"%PDF-"):
                return make_response(400, "The attachment is not a valid PDF.")

            file_key = f"{feedback_id}.pdf"

            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=file_key,
                Body=pdf_data,
                ContentType="application/pdf",
            )

            file_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": file_key},
                ExpiresIn=86400,
            )

        # Save feedback
        table = dynamodb.Table(TABLE_NAME)

        table.put_item(
            Item={
                "feedback_id": feedback_id,
                "name": name,
                "email": email,
                "message": message,
                "file_url": file_url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Notify administrator
        ses.send_email(
            Source=ADMIN_EMAIL,
            Destination={"ToAddresses": [ADMIN_EMAIL]},
            Message={
                "Subject": {
                    "Data": "New Feedback Received",
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Html": {
                        "Data": build_email(name, email, message, file_url),
                        "Charset": "UTF-8",
                    }
                },
            },
        )

        logger.info("Feedback processed: %s", feedback_id)

        return make_response(
            200,
            "Feedback submitted successfully.",
            feedback_id,
        )

    except ClientError:
        logger.exception("AWS service error while processing feedback.")
        return make_response(
            500, "Unable to process feedback. Please try again."
        )

    except Exception:
        logger.exception("Unexpected error while processing feedback.")
        return make_response(
            500, "Unable to process feedback. Please try again."
        )
