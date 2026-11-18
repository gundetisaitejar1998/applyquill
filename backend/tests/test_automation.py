import asyncio
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from backend.app.services import automation


class Handler(BaseHTTPRequestHandler):
    body = b"""<html><body><h1>Application</h1><form>
      <label>Full name <input name='name'></label>
      <label>Email <input type='email' name='email'></label>
      <button>Submit application</button></form></body></html>"""
    def do_GET(self):
        self.send_response(200);self.send_header("Content-Type","text/html");self.end_headers();self.wfile.write(self.body)
    def log_message(self,*args):pass


class BrowserAutomationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server=HTTPServer(("127.0.0.1",0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.tmp=tempfile.TemporaryDirectory();self.old_profile=automation.PROFILE_ROOT;automation.PROFILE_ROOT=Path(self.tmp.name)
    async def asyncTearDown(self):
        self.server.shutdown();self.thread.join(timeout=2);self.server.server_close();automation.PROFILE_ROOT=self.old_profile;self.tmp.cleanup()

    async def test_local_form_fills_known_fields_and_never_submits(self):
        result=await automation.prepare_application(f"http://127.0.0.1:{self.server.server_port}/apply",
            {"name":"Fixture Candidate","email":"fixture@example.test"},candidate_id=1,timeout_ms=10000)
        self.assertEqual(result["status"],"prepared",result)
        self.assertIn("name",result["filled"])
        self.assertIn("email",result["filled"])
        self.assertIn("dry-run",result["reason"])

    async def test_verification_challenge_is_detected_and_skipped(self):
        Handler.body=b"<html><body>Verify your identity with one-time password</body></html>"
        result=await automation.prepare_application(f"http://127.0.0.1:{self.server.server_port}/apply",{},candidate_id=2,timeout_ms=10000)
        self.assertEqual(result["status"],"verification_required")

    async def test_resume_file_is_attached_to_local_fixture_form(self):
        Handler.body=b"<html><body><h1>Application</h1><form><label>Resume <input type='file' name='resume'></label></form></body></html>"
        resume=Path(self.tmp.name)/"resume.pdf";resume.write_bytes(b"fixture resume bytes")
        result=await automation.prepare_application(f"http://127.0.0.1:{self.server.server_port}/apply",{},str(resume),candidate_id=3,timeout_ms=10000)
        self.assertEqual(result["status"],"prepared");self.assertIn("resume",result["filled"])

    async def test_ats_detection_and_confirmation_phrase(self):
        self.assertEqual(automation.ats_for_url("https://boards.greenhouse.io/example"),"greenhouse")
        self.assertEqual(automation.ats_for_url("https://jobs.lever.co/example"),"lever")
        self.assertRegex("Thank you for applying. Your application has been received.",automation.CONFIRMATION)


if __name__=="__main__":unittest.main()
