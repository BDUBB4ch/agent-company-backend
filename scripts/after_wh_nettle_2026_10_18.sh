#!/bin/bash
# After Witch Hazel's build: Ilnora finishes the Nettle redo (parts 5-8, check, send). Log: data/after_wh_nettle_2026_10_18.log
cd "$(dirname "$0")/.."
LOG=data/after_wh_nettle_2026_10_18.log
say() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
ask() { curl -s -m 1500 -X POST http://127.0.0.1:8420/api/chat -H "Content-Type: application/json" --data-binary @"data/review_2026_10_18/chain/$1.json" -o "data/review_2026_10_18/chain/$1.reply2.json"
        say "reply $1: $(python -X utf8 -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print(' '.join(str(d.get('reply')).split())[:220],'| tools',[t.get('name') if isinstance(t,dict) else t for t in d.get('tool_calls') or []])" "data/review_2026_10_18/chain/$1.reply2.json")"; }
queued() { python -X utf8 -c "
import json,glob
print(' | '.join(j['pkg']['title'][:30] for j in (json.load(open(f,encoding='utf-8')) for f in glob.glob('data/video_queue/job_*.json')) if j.get('status') in ('queued','building')))"; }
n=0; while [ -e data/reel_building.flag ] || [ -e data/video_rendering.flag ]; do n=$((n+1)); [ $n -gt 360 ] && { say "gave up"; exit 1; }; sleep 60; done
sleep 120; say "Witch Hazel build over"
for k in nettle2 nettle3 nettle4 nettle4; do
  ask $k; q=$(queued); say "in line: $q"
  case "$q" in *Nettle*) say "nettle sent"; break;; esac
  sleep 20
done
say done
