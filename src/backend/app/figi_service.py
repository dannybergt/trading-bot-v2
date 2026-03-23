import os
import logging
import re
import requests

logger = logging.getLogger(__name__)

class FigiService:
    """Service to interact with the OpenFIGI API for identifier mapping."""
    def __init__(self):
        self.api_key = os.getenv("OPENFIGI_API_KEY", "")
        self.base_url = "https://api.openfigi.com/v3/mapping"

    def _get_headers(self):
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-OPENFIGI-APIKEY'] = self.api_key
        return headers

    def is_isin(self, query: str) -> bool:
        """Basic check if a string looks like an ISIN (12 chars, starts with 2 letters)."""
        return bool(re.match(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$', query.upper()))

    def is_wkn(self, query: str) -> bool:
        """Basic check if a string looks like a WKN (6 alphanumeric chars)."""
        return bool(re.match(r'^[A-Z0-9]{6}$', query.upper()))

    def map_to_ticker(self, id_type: str, id_value: str) -> str:
        """Uses OpenFIGI mapping endpoint to find a ticker for a given identifier."""
        payload = [{'idType': id_type, 'idValue': id_value}]
        try:
            res = requests.post(self.base_url, headers=self._get_headers(), json=payload, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data and isinstance(data, list) and 'data' in data[0]:
                    matches = data[0]['data']
                    # Try to prioritize US exchanges if multiple are returned
                    us_matches = [m for m in matches if m.get('exchCode') in ['US', 'UW', 'UN', 'UQ']]
                    if us_matches:
                        return us_matches[0].get('ticker')
                        
                    # Otherwise return the first ticker found
                    for match in matches:
                        if match.get('ticker'):
                            return match['ticker']
        except Exception:
            logger.exception("figi_mapping_failed id_type=%s id_value=%s", id_type, id_value)
        return None

    def get_ticker_by_isin(self, isin: str) -> str:
        return self.map_to_ticker('ID_ISIN', isin.upper())

    def get_ticker_by_wkn(self, wkn: str) -> str:
        return self.map_to_ticker('ID_WERTPAPIER', wkn.upper())

figi = FigiService()
