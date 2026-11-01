import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil

from core.tools.calendar_tool import CalendarTool
from core.tools.clipboard_tool import ClipboardTool
from core.tools.dev_port_tool import DevPortTool
from core.tools.github_tool import GitHubTool
from core.tools.notes_tool import NotesDatabase, NotesTool
from core.tools.timer_tool import TimerTool
from core.tools.youtube_tool import YouTubeTool


# ==============================================================================
# 1. TIMER TOOL TESTS
# ==============================================================================
class TestTimerTool:
    def test_start_timer_seconds(self) -> None:
        notifier = MagicMock()
        tool = TimerTool(notifier=notifier)

        res = tool.execute(action="start", duration_seconds=10, label="Test Timer")
        assert res["success"] is True
        assert res["action"] == "start"
        assert res["label"] == "Test Timer"
        assert res["duration_seconds"] == 10.0
        assert "timer_id" in res

        # Clean up
        tool.execute(action="cancel", cancel_all=True)

    def test_start_timer_minutes(self) -> None:
        notifier = MagicMock()
        tool = TimerTool(notifier=notifier)

        res = tool.execute(action="start", minutes=2, label="Cooking")
        assert res["success"] is True
        assert res["duration_seconds"] == 120.0
        assert res["formatted_duration"] == "2min"

        tool.execute(action="cancel", cancel_all=True)

    def test_start_pomodoro(self) -> None:
        tool = TimerTool(notifier=MagicMock())
        res = tool.execute(action="pomodoro", minutes=25)
        assert res["success"] is True
        assert res["duration_seconds"] == 1500.0
        assert "Pomodoro" in res["label"]

        tool.execute(action="cancel", cancel_all=True)

    def test_list_and_cancel_timers(self) -> None:
        tool = TimerTool(notifier=MagicMock())
        t1 = tool.execute(action="start", duration_seconds=100, label="Task 1")
        tool.execute(action="start", duration_seconds=200, label="Task 2")

        listing = tool.execute(action="list")
        assert listing["success"] is True
        assert listing["count"] == 2

        # Cancel single timer by id
        c1 = tool.execute(action="cancel", timer_id=t1["timer_id"])
        assert c1["success"] is True

        listing2 = tool.execute(action="list")
        assert listing2["count"] == 1

        # Cancel all remaining
        c_all = tool.execute(action="cancel", cancel_all=True)
        assert c_all["success"] is True
        assert c_all["cancelled_count"] == 1

        listing3 = tool.execute(action="list")
        assert listing3["count"] == 0

    def test_timer_trigger_callbacks(self) -> None:
        notifier = MagicMock()
        tts_mock = MagicMock()
        tool = TimerTool(notifier=notifier, tts_callback=tts_mock)

        tool._on_timer_triggered("tid-123", "Alarme Forno")
        notifier.notify.assert_called_once()
        tts_mock.assert_called_once_with(
            "Atenção: o timer de Alarme Forno acabou de terminar."
        )


# ==============================================================================
# 2. CLIPBOARD TOOL TESTS
# ==============================================================================
class TestClipboardTool:
    @patch("pyperclip.paste", return_value="Hello World from Clipboard!")
    def test_clipboard_read(self, mock_paste: MagicMock) -> None:
        tool = ClipboardTool()
        res = tool.execute(action="read")
        assert res["success"] is True
        assert res["content"] == "Hello World from Clipboard!"
        assert res["length"] == len("Hello World from Clipboard!")
        assert res["truncated"] is False

    @patch("pyperclip.paste", return_value="")
    def test_clipboard_read_empty(self, mock_paste: MagicMock) -> None:
        tool = ClipboardTool()
        res = tool.execute(action="read")
        assert res["success"] is True
        assert res["content"] == ""
        assert "vazia" in res["message"]

    @patch("pyperclip.paste", return_value="A" * 500)
    def test_clipboard_read_truncated(self, mock_paste: MagicMock) -> None:
        tool = ClipboardTool(max_chars=100)
        res = tool.execute(action="read")
        assert res["success"] is True
        assert res["truncated"] is True
        assert "truncado" in res["content"]

    @patch("pyperclip.copy")
    def test_clipboard_write(self, mock_copy: MagicMock) -> None:
        tool = ClipboardTool()
        res = tool.execute(action="write", content="New copied text")
        assert res["success"] is True
        assert res["length"] == len("New copied text")
        mock_copy.assert_called_once_with("New copied text")


# ==============================================================================
# 3. NOTES TOOL TESTS
# ==============================================================================
class TestNotesTool:
    def test_notes_and_reminders_lifecycle(self, tmp_path: Path) -> None:
        db = NotesDatabase(tmp_path / "notes.db")
        tool = NotesTool(db=db, markdown_dir=tmp_path)

        # 1. Add notes
        n1 = tool.execute(
            action="add_note", content="Revisar arquitetura do Jarvis", tag="dev"
        )
        assert n1["success"] is True
        assert n1["note_id"] == 1
        assert n1["markdown_synced"] is True

        n2 = tool.execute(
            action="add_note", content="Comprar café especial", tag="pessoal"
        )
        assert n2["success"] is True

        # Check markdown file created
        md_files = list(tmp_path.glob("Jarvis_Notes_*.md"))
        assert len(md_files) == 1
        md_content = md_files[0].read_text(encoding="utf-8")
        assert "Revisar arquitetura do Jarvis" in md_content

        # 2. List & Search notes
        notes_list = tool.execute(action="list_notes")
        assert notes_list["success"] is True
        assert notes_list["count"] == 2

        search_res = tool.execute(action="search_notes", query="arquitetura")
        assert search_res["success"] is True
        assert search_res["count"] == 1
        assert "Revisar arquitetura" in search_res["notes"][0]["content"]

        # 3. Add & complete reminders
        r1 = tool.execute(action="add_reminder", content="Enviar relatório semanal")
        assert r1["success"] is True
        assert r1["status"] == "pending"

        rems = tool.execute(action="list_reminders")
        assert rems["count"] == 1

        comp = tool.execute(action="complete_reminder", reminder_id=r1["reminder_id"])
        assert comp["success"] is True

        rems_after = tool.execute(action="list_reminders")
        assert rems_after["count"] == 0


# ==============================================================================
# 4. YOUTUBE TOOL TESTS
# ==============================================================================
class TestYouTubeTool:
    @patch("os.startfile")
    def test_youtube_search_page(self, mock_startfile: MagicMock) -> None:
        tool = YouTubeTool()
        res = tool.execute(action="search", query="python tutorial")
        assert res["success"] is True
        assert "youtube.com/results" in res["url"]
        mock_startfile.assert_called_once()

    @patch("os.startfile")
    @patch("urllib.request.urlopen")
    def test_youtube_play_video_match(
        self, mock_urlopen: MagicMock, mock_startfile: MagicMock
    ) -> None:
        # Mock HTML response containing a videoId with spaces
        mock_html = b'<html><body><script>var data = {"videoId": "dQw4w9WgXcQ"};</script></body></html>'
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_html
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        tool = YouTubeTool()
        res = tool.execute(action="play", query="never gonna give you up")

        assert res["success"] is True
        assert res["video_id"] == "dQw4w9WgXcQ"
        assert res["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        mock_startfile.assert_called_once_with(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )


# ==============================================================================
# 5. GITHUB & DEV PORT TOOL TESTS
# ==============================================================================
class TestGitHubAndDevPortTools:
    @patch("subprocess.run")
    def test_github_pr_list(self, mock_run: MagicMock) -> None:
        fake_prs = [
            {
                "number": 42,
                "title": "feat: new audio cue",
                "author": {"login": "dev1"},
                "headRefName": "feature/cue",
                "url": "https://github.com/Leturnos/python-jarvis/pull/42",
            }
        ]
        mock_proc = MagicMock()
        mock_proc.stdout = json.dumps(fake_prs)
        mock_run.return_value = mock_proc

        tool = GitHubTool()
        res = tool.execute(action="pr_list", limit=5)
        assert res["success"] is True
        assert res["count"] == 1
        assert res["pull_requests"][0]["number"] == 42

    @patch("psutil.net_connections")
    def test_dev_port_inspect_free(self, mock_net: MagicMock) -> None:
        mock_net.return_value = []
        tool = DevPortTool()
        res = tool.execute(action="inspect", port=3000)
        assert res["success"] is True
        assert res["occupied"] is False

    @patch("psutil.Process")
    @patch("psutil.net_connections")
    def test_dev_port_inspect_occupied(
        self, mock_net: MagicMock, mock_proc_cls: MagicMock
    ) -> None:
        conn = MagicMock()
        conn.status = getattr(psutil, "CONN_LISTEN", "LISTEN")
        conn.laddr.port = 8080
        conn.pid = 9999
        mock_net.return_value = [conn]

        mock_proc = MagicMock()
        mock_proc.name.return_value = "node.exe"
        mock_proc.memory_info.return_value.rss = 100 * 1024 * 1024
        mock_proc.cmdline.return_value = ["node", "server.js"]
        mock_proc_cls.return_value = mock_proc

        tool = DevPortTool()
        res = tool.execute(action="inspect", port=8080)
        assert res["success"] is True
        assert res["occupied"] is True
        assert res["process"]["name"] == "node.exe"

    def test_dev_port_kill_system_protection(self) -> None:
        conn = MagicMock()
        conn.status = getattr(psutil, "CONN_LISTEN", "LISTEN")
        conn.laddr.port = 80
        conn.pid = 4  # System PID
        with patch("psutil.net_connections", return_value=[conn]):
            tool = DevPortTool()
            res = tool.execute(action="kill", port=80, authorized=True)
            assert res["success"] is False
            assert "Kernel/Sistema" in res["error"]

    def test_dev_port_kill_unauthorized_rejection(self) -> None:
        tool = DevPortTool()
        res = tool.execute(action="kill", port=8080, authorized=False)
        assert res["success"] is False
        assert "autoriz" in res["error"].lower()

    @patch("psutil.Process")
    @patch("psutil.net_connections")
    def test_dev_port_kill_authorized_success(
        self, mock_net: MagicMock, mock_proc_cls: MagicMock
    ) -> None:
        conn = MagicMock()
        conn.status = getattr(psutil, "CONN_LISTEN", "LISTEN")
        conn.laddr.port = 8080
        conn.pid = 9999
        mock_net.return_value = [conn]

        mock_proc = MagicMock()
        mock_proc.name.return_value = "python.exe"
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock()
        mock_proc_cls.return_value = mock_proc

        tool = DevPortTool()
        res = tool.execute(action="kill", port=8080, authorized=True)
        assert res["success"] is True
        assert res["action"] == "kill"
        assert res["killed_pid"] == 9999
        mock_proc.terminate.assert_called_once()


# ==============================================================================
# 6. CALENDAR TOOL TESTS
# ==============================================================================
class TestCalendarTool:
    def test_parse_ics_events_and_filter(self) -> None:
        now = datetime.now().astimezone()
        today_str = now.strftime("%Y%m%d")
        tomorrow_str = (now + timedelta(days=1)).strftime("%Y%m%d")

        ics_sample = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Jarvis//Test//EN
BEGIN:VEVENT
SUMMARY:Reunião Daily
DTSTART;TZID="America/Sao_Paulo":{today_str}T100000
DTEND;TZID="America/Sao_Paulo":{today_str}T103000
LOCATION:Google Meet
DESCRIPTION:Alinhamento diário do time
END:VEVENT
BEGIN:VEVENT
SUMMARY:Review com Cliente
DTSTART:{tomorrow_str}T150000Z
DTEND:{tomorrow_str}T160000Z
LOCATION:Teams
END:VEVENT
BEGIN:VEVENT
SUMMARY:Feriado Nacional
DTSTART:{today_str}
END:VEVENT
END:VCALENDAR
"""
        tool = CalendarTool()
        events = tool._parse_ics_events(ics_sample)
        assert len(events) == 3
        assert events[0].summary == "Feriado Nacional"
        assert events[0].is_all_day is True
        assert events[0].to_dict()["formatted_time"] == "Dia inteiro"
        assert events[1].summary == "Reunião Daily"
        assert events[1].location == "Google Meet"
        assert events[2].summary == "Review com Cliente"

        today_filtered = tool._filter_events(events, period="today", limit=5)
        assert len(today_filtered) == 2

        tomorrow_filtered = tool._filter_events(events, period="tomorrow", limit=5)
        assert len(tomorrow_filtered) == 1
        assert tomorrow_filtered[0].summary == "Review com Cliente"

    def test_calendar_ssrf_protection(self) -> None:
        assert (
            CalendarTool._is_safe_url("http://169.254.169.254/latest/meta-data")
            is False
        )
        assert CalendarTool._is_safe_url("http://localhost:8000/cal.ics") is False
        assert CalendarTool._is_safe_url("http://127.0.0.1:5000/cal.ics") is False
        assert CalendarTool._is_safe_url("file:///etc/passwd") is False
        assert (
            CalendarTool._is_safe_url(
                "https://calendar.google.com/calendar/ical/user/basic.ics"
            )
            is True
        )

    def test_calendar_execute_with_file(self, tmp_path: Path) -> None:
        from core.security.path_guard import PathGuard

        ics_file = tmp_path / "test.ics"
        now = datetime.now().astimezone()
        today_str = now.strftime("%Y%m%d")
        ics_file.write_text(
            f"BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nSUMMARY:Daily Scrum\nDTSTART:{today_str}T090000Z\nDTEND:{today_str}T093000Z\nEND:VEVENT\nEND:VCALENDAR\n",
            encoding="utf-8",
        )

        guard = PathGuard(allowed_workspaces=[tmp_path])
        tool = CalendarTool(path_guard=guard)
        res = tool.execute(action="today", ics_url=str(ics_file))
        assert res["success"] is True
        assert res["count"] == 1
        assert res["events"][0]["title"] == "Daily Scrum"

    def test_calendar_execute_missing_source(self) -> None:
        tool = CalendarTool(ics_url="")
        res = tool.execute(action="today", ics_url="")
        assert res["success"] is False
        assert "nenhum link ou arquivo" in res["error"].lower()

    def test_calendar_execute_unsafe_url(self) -> None:
        tool = CalendarTool()
        res = tool.execute(action="today", ics_url="http://169.254.169.254/meta")
        assert res["success"] is False
        assert "insegura" in res["error"].lower()


# ==============================================================================
# 7. ADDITIONAL HIGH-COVERAGE TESTS
# ==============================================================================
class TestToolsAdditionalCoverage:
    @patch("subprocess.run")
    def test_github_issue_list(self, mock_run: MagicMock) -> None:
        fake_issues = [
            {
                "number": 10,
                "title": "Bug in audio",
                "author": {"login": "tester"},
                "labels": [{"name": "bug"}],
                "url": "https://github.com/Leturnos/python-jarvis/issues/10",
            }
        ]
        mock_proc = MagicMock()
        mock_proc.stdout = json.dumps(fake_issues)
        mock_run.return_value = mock_proc

        tool = GitHubTool()
        res = tool.execute(action="issue_list", limit=3)
        assert res["success"] is True
        assert res["count"] == 1
        assert res["issues"][0]["number"] == 10

    @patch("subprocess.run")
    def test_github_ci_status(self, mock_run: MagicMock) -> None:
        fake_runs = [
            {
                "databaseId": 123,
                "displayTitle": "CI Workflow",
                "status": "completed",
                "conclusion": "success",
                "workflowName": "CI",
                "headBranch": "main",
            }
        ]
        mock_proc = MagicMock()
        mock_proc.stdout = json.dumps(fake_runs)
        mock_run.return_value = mock_proc

        tool = GitHubTool()
        res = tool.execute(action="ci_status", limit=2)
        assert res["success"] is True
        assert res["count"] == 1
        assert res["runs"][0]["conclusion"] == "success"

    @patch("subprocess.run")
    def test_github_pr_status(self, mock_run: MagicMock) -> None:
        fake_status = {
            "currentBranch": {"title": "feat: pr status"},
            "createdBy": [],
            "needsReview": [],
        }
        mock_proc = MagicMock()
        mock_proc.stdout = json.dumps(fake_status)
        mock_run.return_value = mock_proc

        tool = GitHubTool()
        res = tool.execute(action="pr_status")
        assert res["success"] is True
        assert "currentBranch" in res["status"]

    @patch("subprocess.run", side_effect=FileNotFoundError("gh not found"))
    def test_github_cli_not_found(self, mock_run: MagicMock) -> None:
        tool = GitHubTool()
        res = tool.execute(action="pr_list")
        assert res["success"] is False
        assert "não foi encontrado" in res["error"]

    def test_github_unknown_action(self) -> None:
        tool = GitHubTool()
        res = tool.execute(action="unknown_action_xyz")
        assert res["success"] is False
        assert "desconhecida" in res["error"]

    @patch("psutil.Process")
    @patch("psutil.net_connections")
    def test_dev_port_list_all_ports(
        self, mock_net: MagicMock, mock_proc_cls: MagicMock
    ) -> None:
        conn1 = MagicMock()
        conn1.status = getattr(psutil, "CONN_LISTEN", "LISTEN")
        conn1.laddr.port = 3000
        conn1.laddr.ip = "127.0.0.1"
        conn1.pid = 1111

        conn2 = MagicMock()
        conn2.status = getattr(psutil, "CONN_LISTEN", "LISTEN")
        conn2.laddr.port = 5000
        conn2.laddr.ip = "0.0.0.0"
        conn2.pid = 2222

        mock_net.return_value = [conn1, conn2]

        mock_proc = MagicMock()
        mock_proc.name.return_value = "python.exe"
        mock_proc_cls.return_value = mock_proc

        tool = DevPortTool()
        res = tool.execute(action="inspect")
        assert res["success"] is True
        assert res["count"] == 2
        assert len(res["ports"]) == 2

    def test_dev_port_is_destructive_action(self) -> None:
        assert DevPortTool.is_destructive_action("kill") is True
        assert DevPortTool.is_destructive_action("KILL") is True
        assert DevPortTool.is_destructive_action({"action": "kill"}) is True
        assert DevPortTool.is_destructive_action("inspect") is False
        assert DevPortTool.is_destructive_action({"action": "inspect"}) is False
        assert DevPortTool.is_destructive_action(None) is False

    def test_dev_port_unknown_action(self) -> None:
        tool = DevPortTool()
        res = tool.execute(action="explode_server")
        assert res["success"] is False
        assert "desconhecida" in res["error"]

    def test_notes_reminders_crud(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test_notes.db"
        db = NotesDatabase(db_path=db_path)
        tool = NotesTool(db=db)

        r1 = tool.execute(action="add_reminder", content="Comprar café")
        assert r1["success"] is True
        assert "reminder_id" in r1

        listing = tool.execute(action="list_reminders")
        assert listing["success"] is True
        assert listing["count"] == 1
        assert listing["reminders"][0]["content"] == "Comprar café"

        comp = tool.execute(action="complete_reminder", reminder_id=r1["reminder_id"])
        assert comp["success"] is True

        listing2 = tool.execute(action="list_reminders")
        assert listing2["count"] == 0

    def test_notes_markdown_file_append(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test_notes.db"
        db = NotesDatabase(db_path=db_path)
        tool = NotesTool(db=db, markdown_dir=tmp_path)

        res = tool.execute(
            action="add_note", content="Planejar Sprint 3", tag="planning"
        )
        assert res["success"] is True

        today_str = datetime.now().strftime("%Y-%m-%d")
        md_file = tmp_path / f"Jarvis_Notes_{today_str}.md"
        assert md_file.exists()
        content = md_file.read_text(encoding="utf-8")
        assert "Planejar Sprint 3" in content
        assert "#planning" in content

    def test_timer_invalid_duration(self) -> None:
        tool = TimerTool(notifier=MagicMock())
        res = tool.execute(action="start", duration_seconds=-5)
        assert res["success"] is False
        assert "maior que zero" in res["error"].lower()

    def test_timer_unknown_action(self) -> None:
        tool = TimerTool(notifier=MagicMock())
        res = tool.execute(action="fly_to_moon")
        assert res["success"] is False
        assert "desconhecida" in res["error"].lower()

    def test_youtube_missing_query(self) -> None:
        tool = YouTubeTool()
        res = tool.execute(action="play", query="")
        assert res["success"] is False
        assert "termo de busca" in res["error"].lower()

    @patch("pyperclip.paste", return_value="")
    def test_clipboard_empty_content(self, mock_paste: MagicMock) -> None:
        tool = ClipboardTool()
        res = tool.execute(action="read")
        assert res["success"] is True
        assert res["content"] == ""
        assert "vazia" in res["message"].lower()
