#!/bin/bash
# Setup Script for Slack Webhook Configuration

set -e

echo "=========================================="
echo "  Slack Webhook Configuration Helper"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "[INFO] Creating .env from .env.example..."
    cp .env.example .env
    echo "[SUCCESS] .env file created!"
else
    echo "[INFO] .env file already exists"
fi

echo ""
echo "📋 To get your Slack webhook URL:"
echo "   1. Go to: https://api.slack.com/apps"
echo "   2. Create a new app (or use existing)"
echo "   3. Enable 'Incoming Webhooks'"
echo "   4. Add webhook to your workspace"
echo "   5. Copy the webhook URL"
echo ""

read -p "Do you have your Slack webhook URL? (y/n): " has_webhook

if [ "$has_webhook" = "y" ] || [ "$has_webhook" = "Y" ]; then
    echo ""
    read -p "Enter your Slack webhook URL: " webhook_url
    
    # Validate URL format
    if [[ ! "$webhook_url" =~ ^https://hooks.slack.com/services/ ]]; then
        echo "[ERROR] Invalid webhook URL format. Should start with: https://hooks.slack.com/services/"
        exit 1
    fi
    
    # Update .env file
    if grep -q "^SLACK_WEBHOOK_URL=" .env; then
        # Replace existing
        sed -i "s|^SLACK_WEBHOOK_URL=.*|SLACK_WEBHOOK_URL=${webhook_url}|" .env
        echo "[SUCCESS] Updated SLACK_WEBHOOK_URL in .env"
    else
        # Add new
        echo "SLACK_WEBHOOK_URL=${webhook_url}" >> .env
        echo "[SUCCESS] Added SLACK_WEBHOOK_URL to .env"
    fi
    
    echo ""
    echo "✅ Configuration complete!"
    echo ""
    echo "🧪 Test your webhook:"
    echo "   curl -X POST \"${webhook_url}\" \\"
    echo "     -H 'Content-Type: application/json' \\"
    echo "     -d '{\"text\":\"🎉 Webhook test successful!\"}'"
    echo ""
    
    read -p "Would you like to test the webhook now? (y/n): " test_webhook
    
    if [ "$test_webhook" = "y" ] || [ "$test_webhook" = "Y" ]; then
        echo ""
        echo "[INFO] Sending test message to Slack..."
        
        response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${webhook_url}" \
            -H 'Content-Type: application/json' \
            -d '{"text":"🎉 Webhook test successful! Your Stage 3 observability is ready."}')
        
        if [ "$response" = "200" ]; then
            echo "[SUCCESS] ✅ Test message sent! Check your Slack channel."
        else
            echo "[ERROR] ❌ Test failed with HTTP $response"
        fi
    fi
else
    echo ""
    echo "⚠️  Please get your webhook URL first:"
    echo "   Visit: https://api.slack.com/apps"
    echo "   Then run this script again"
fi

echo ""
echo "=========================================="
echo "  Next Steps:"
echo "=========================================="
echo "1. Verify webhook in .env file"
echo "2. Deploy with: docker-compose up -d --build"
echo "3. Generate traffic to test alerts"
echo "4. Check watcher logs: docker logs -f alert_watcher"
echo ""
