#!/bin/bash
# Verify Notion sync is working by checking for test entry in PostgreSQL

set -e

echo "🔍 Notion Integration Verification Script"
echo "=========================================="
echo ""

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL environment variable not set"
    echo "   For local testing, set it in .env file"
    exit 1
fi

echo "✅ DATABASE_URL is set"
echo ""

# Expected test entry details
EXPECTED_TITLE="Test Video - Pikachu Forest Adventure"
EXPECTED_NOTION_PAGE_ID="2e8088e8-988b-81d4-93bd-eeb49e35233e"

echo "🔎 Checking for test entry in PostgreSQL..."
echo "   Expected Title: $EXPECTED_TITLE"
echo "   Expected notion_page_id: $EXPECTED_NOTION_PAGE_ID"
echo ""

# Query the database
echo "📊 Running SQL query..."
QUERY="SELECT
    id,
    title,
    status,
    channel_id,
    notion_page_id,
    created_at
FROM tasks
WHERE notion_page_id = '$EXPECTED_NOTION_PAGE_ID'
   OR title = '$EXPECTED_TITLE';"

# Try to query using psql if available
if command -v psql &> /dev/null; then
    echo ""
    echo "Using psql to query database:"
    echo "$QUERY"
    echo ""

    psql "$DATABASE_URL" -c "$QUERY" || {
        echo ""
        echo "❌ psql query failed"
        echo "   Make sure your DATABASE_URL is correct"
        exit 1
    }

    echo ""
    echo "✅ Query executed successfully"
    echo ""
    echo "🎯 What to look for:"
    echo "   - One row returned with title: $EXPECTED_TITLE"
    echo "   - status should be: 'queued'"
    echo "   - notion_page_id should be: $EXPECTED_NOTION_PAGE_ID"
    echo "   - channel_id should be: 'poke1'"
    echo ""
else
    echo "⚠️  psql not found in PATH"
    echo ""
    echo "📋 Manual verification:"
    echo "   Connect to your database and run this query:"
    echo ""
    echo "$QUERY"
    echo ""
fi

echo "📝 Additional verification steps:"
echo ""
echo "1. Check application logs:"
echo "   railway logs --filter 'task_enqueued_from_notion' | tail -20"
echo ""
echo "2. Expected log entry:"
echo "   task_enqueued_from_notion"
echo "   notion_page_id=2e8088e8-988b-81d4-93bd-eeb49e35233e"
echo "   task_id=<some-uuid>"
echo "   title=\"Test Video - Pikachu Forest Adventure\""
echo ""
echo "3. Check for any sync errors:"
echo "   railway logs --filter 'notion_database_query_failed' | tail -20"
echo ""
echo "4. View the test entry in Notion:"
echo "   https://www.notion.so/2e8088e8988b81d493bdeeb49e35233e"
echo ""

# Check if entry exists
if command -v psql &> /dev/null; then
    COUNT=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM tasks WHERE notion_page_id = '$EXPECTED_NOTION_PAGE_ID';")
    COUNT=$(echo $COUNT | tr -d ' ')

    if [ "$COUNT" = "1" ]; then
        echo "✅ SUCCESS: Test entry found in database!"
        echo "   Notion sync is working correctly ✨"
        exit 0
    elif [ "$COUNT" = "0" ]; then
        echo "⚠️  WARNING: Test entry NOT found in database"
        echo ""
        echo "🔧 Troubleshooting:"
        echo "   1. Wait 60 seconds for sync loop to run"
        echo "   2. Check if NOTION_DATABASE_IDS includes: 6b870ef4134346168f14367291bc89e6"
        echo "   3. Verify database is shared with your integration"
        echo "   4. Check logs for errors: railway logs --filter 'notion'"
        echo "   5. Run diagnostic: python scripts/test_notion_integration.py"
        exit 1
    else
        echo "⚠️  WARNING: Multiple entries found ($COUNT)"
        echo "   This might indicate duplicate syncing"
        exit 1
    fi
fi
