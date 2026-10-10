import io
import unittest
from unittest.mock import patch
import launch
import server
from types import SimpleNamespace


class LaunchTests(unittest.TestCase):
    def test_open_reuses_existing_service(self):
        with patch('sys.argv',['launch.py']), patch.object(launch,'ready',return_value=True), patch.object(launch.subprocess,'Popen') as process, patch.object(launch.webbrowser,'open',return_value=True) as browser, patch('sys.stdout',new=io.StringIO()):
            launch.main()
        process.assert_not_called()
        browser.assert_called_once_with(launch.URL)

    def test_stop_waits_for_service_without_reopening_browser(self):
        with patch('sys.argv',['launch.py','--stop']), patch.object(launch,'ready',side_effect=[True,False]), patch.object(launch,'urlopen') as request, patch.object(launch.webbrowser,'open') as browser, patch('sys.stdout',new=io.StringIO()):
            launch.main()
        self.assertEqual(request.call_args.args[0].full_url,launch.URL+'/api/shutdown')
        browser.assert_not_called()

    def test_stop_when_service_is_already_closed(self):
        with patch('sys.argv',['launch.py','--stop']), patch.object(launch,'ready',return_value=False), patch.object(launch.subprocess,'Popen') as process, patch('sys.stdout',new=io.StringIO()):
            launch.main()
        process.assert_not_called()

    def test_busy_or_old_service_rejection_is_reported(self):
        with patch('sys.argv',['launch.py','--restart']), patch.object(launch,'ready',return_value=True), patch.object(launch,'urlopen',side_effect=OSError('busy')):
            with self.assertRaisesRegex(RuntimeError,'确认模拟已经结束'): launch.main()

    def test_shutdown_rejects_running_job(self):
        handler=object.__new__(server.Handler)
        handler.path='/api/shutdown'; handler.headers={}
        handler.server=SimpleNamespace(server_port=8766)
        with patch.dict(server.JOB,{'running':True}), patch.object(handler,'respond') as respond:
            handler.do_POST()
        self.assertEqual(respond.call_args.args[1],409)

    def test_shutdown_rejects_external_origin(self):
        handler=object.__new__(server.Handler)
        handler.path='/api/shutdown'; handler.headers={'Origin':'https://example.com'}
        handler.server=SimpleNamespace(server_port=8766)
        with patch.object(handler,'respond') as respond: handler.do_POST()
        self.assertEqual(respond.call_args.args[1],403)


if __name__=='__main__': unittest.main()
