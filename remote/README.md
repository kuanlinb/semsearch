# Remote reranker (optional)

A cross-encoder reranker (bge-reranker-v2-m3) improves the order of the top results, but takes
2–4 s per query on a laptop GPU. If you have another machine with a CUDA GPU, it can do the
reranking in tens of milliseconds instead. When that machine is unreachable, SemSearch simply
shows the fast results: each attempt waits at most 3 s, and after a failure the remote
reranker is not tried again for 15 s.

What is sent: the query and, for each of the top `rerank_top` results, its name text and one
snippet (up to 400 characters). Nothing is stored on the remote machine.

## 1. On the GPU machine

Needs Python with `torch` (CUDA build) and `transformers`:

```bash
pip install torch transformers
python rerank_server.py            # options: --port 8798 --model BAAI/bge-reranker-v2-m3 --idle-minutes 15
```

The server listens on `127.0.0.1` only and rejects requests whose `Host` header is not
`127.0.0.1:<port>` or `localhost:<port>`. The model is downloaded on the first request, loaded
on demand, and unloaded after 15 idle minutes to free GPU memory.

Keep it running however you like, e.g. a systemd user service on Linux, or a scheduled task
on Windows. A PowerShell sketch for Windows (replace the placeholders):

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\path\to\python.exe" `
             -Argument "C:\path\to\rerank_server.py" -WorkingDirectory "C:\path\to"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$set     = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 3 `
             -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "SemSearchRerank" -Action $action -Trigger $trigger -Settings $set
```

## 2. On the Mac

Make sure `ssh my-gpu-box` works without a password prompt (key-based login, e.g. a `Host`
entry in `~/.ssh/config`), then add to `~/.semsearch/config.json`:

```json
{
  "remote_reranker": "http://127.0.0.1:8798",
  "remote_reranker_ssh": "my-gpu-box"
}
```

and restart SemSearch (quit it from the menu bar and open it again). The search service then
keeps an SSH tunnel `127.0.0.1:8798 → my-gpu-box:127.0.0.1:8798` open and reconnects when it
drops. The local and remote port are the same (the one in `remote_reranker`), so start the
server with a matching `--port` if you change it.

Leave `remote_reranker_ssh` empty if you manage the connection yourself (your own tunnel, a
VPN); `remote_reranker` can then be any URL that reaches the server, keeping in mind that the
server only answers requests addressed to `127.0.0.1` or `localhost`.

The search panel shows "reranked" in its footer when the reranked order arrived.
