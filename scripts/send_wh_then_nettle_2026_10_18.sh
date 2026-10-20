#!/bin/bash
# bash version (the .ps1 broke on the em-dash). Log: data/send_wh_then_nettle_2026_10_18.log
cd "$(dirname "$0")/.."
LOG=data/send_wh_then_nettle_2026_10_18.log
say() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
ask() { curl -s -m 1500 -X POST http://127.0.0.1:8420/api/chat -H "Content-Type: application/json" --data-binary @"data/review_2026_10_18/chain/$1.json" -o "data/review_2026_10_18/chain/$1.reply.json"
        say "reply $1: $(python -X utf8 -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print(' '.join(str(d.get('reply')).split())[:260],'| tools',[t.get('name') if isinstance(t,dict) else t for t in d.get('tool_calls') or []])" "data/review_2026_10_18/chain/$1.reply.json")"; }
queued() { python -X utf8 -c "
import json,glob
print(' | '.join(j['pkg']['title'][:30] for j in (json.load(open(f,encoding='utf-8')) for f in glob.glob('data/video_queue/job_*.json')) if j.get('status') in ('queued','building')))"; }
ask wh_send; say "in line: $(queued)"
for k in nettle1 nettle2 nettle3 nettle4; do
  ask $k; q=$(queued); say "in line: $q"
  case "$q" in *Nettle*) say "nettle sent"; break;; esac
  sleep 20
done
say done
