#!/bin/bash
# Pi Chat Bridge - Workaround for broken CLI polling
# Writes responses from DavidMolt to a file that the dashboard can read

RESPONSE_FILE="$HOME/.openclaw/workspace/dashboard/pi-chat-response.txt"
RESPONSE_ID_FILE="$HOME/.openclaw/workspace/dashboard/pi-chat-last-id.txt"

# Clear old response
rm -f "$RESPONSE_FILE"

# This script should be triggered by the main bot when it sees a [Pi Chat] message
# For now, just exit - the bot will handle writing the response file

exit 0
