"""Safe Dhan API failure diagnostics. Never print server response text/tokens."""
import unittest
from index_research.dhan_data import dhan_error_diagnostic

class DhanErrorDiagnosticTests(unittest.TestCase):
    def test_input_error(self):
        self.assertIn("DH-905",dhan_error_diagnostic(b'{"errorCode":"DH-905","errorMessage":"Missing required request field"}'))
    def test_entitlement(self):
        self.assertIn("subscription",dhan_error_diagnostic(b'{"remarks":{"error_code":"DH-902"}}'))
    def test_invalid_security_id(self):
        self.assertIn("Security ID",dhan_error_diagnostic(b'{"errorCode":813}'))
    def test_never_reflect_secrets(self):
        secret="ACCESS_TOKEN_ABC123"
        response=('{"errorCode":"DH-905","errorMessage":"'+secret+'"}').encode()
        self.assertNotIn(secret,dhan_error_diagnostic(response))
        self.assertNotIn(secret,dhan_error_diagnostic(('{"message":"'+secret+'"}').encode()))
    def test_malformed_server_response(self):
        self.assertIn("No recognized",dhan_error_diagnostic(b'<html>400</html>'))

if __name__ == "__main__":
    unittest.main()
