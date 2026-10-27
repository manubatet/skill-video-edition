#!/usr/bin/env bash
# Builds the Claude Desktop bundle (dist/social-video-editor.mcpb) and the skill zip for
# claude.ai / ChatGPT (dist/social-video-editor-skill.zip). Run from anywhere.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
STAGE="$DIST/mcpb"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp "$ROOT/plugin/claude-desktop/manifest.json" "$STAGE/"
rsync -a --exclude __pycache__ "$ROOT/plugin/server" "$ROOT/plugin/ui" "$STAGE/"
rsync -a --exclude __pycache__ --exclude '*.pyc' "$ROOT/social-video-editor/" "$STAGE/skill/"
rm -f "$DIST/social-video-editor.mcpb" "$DIST/social-video-editor-skill.zip"
(cd "$STAGE" && zip -qr "$DIST/social-video-editor.mcpb" .)
(cd "$ROOT" && zip -qr "$DIST/social-video-editor-skill.zip" social-video-editor -x '*/__pycache__/*' '*.pyc')
rm -rf "$STAGE"
echo "Built:"
ls -lh "$DIST"/*.mcpb "$DIST"/*.zip
