import csv
import json
import os
from app.core.time import utc_now
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.models.models import Company


class ExportService:
    def __init__(self, export_dir: str):
        self.export_dir = export_dir
        os.makedirs(self.export_dir, exist_ok=True)

    def _company_row(self, company: Company) -> Dict[str, Any]:
        emails = [c.value for c in company.contacts if c.type == "EMAIL"]
        phones = [c.value for c in company.contacts if c.type == "PHONE"]
        social_map = {link.platform: link.url for link in company.social_links}
        founder = company.profiles[0].name if company.profiles else None
        founder_linkedin = company.profiles[0].profile_url if company.profiles else None
        source_urls = ", ".join(source.url for source in company.sources)
        return {
            "name": company.name,
            "website": company.website,
            "description": company.description,
            "industry": ", ".join(c.name for c in company.categories),
            "company_size": company.company_size,
            "funding_stage": company.funding_stage,
            "founder": founder,
            "founder_linkedin": founder_linkedin,
            "email": emails[0] if emails else None,
            "all_emails": ", ".join(emails),
            "phone": phones[0] if phones else None,
            "all_phones": ", ".join(phones),
            "linkedin": social_map.get("LINKEDIN"),
            "instagram": social_map.get("INSTAGRAM"),
            "twitter": social_map.get("TWITTER"),
            "facebook": social_map.get("FACEBOOK"),
            "youtube": social_map.get("YOUTUBE"),
            "whatsapp": social_map.get("WHATSAPP"),
            "crunchbase": social_map.get("CRUNCHBASE"),
            "wellfound": social_map.get("WELLFOUNDED"),
            "tracxn": social_map.get("TRACXN"),
            "startup_india_profile": social_map.get("STARTUPINDIA"),
            "city": company.city,
            "state": company.state,
            "country": company.country,
            "lead_score": company.lead_score,
            "confidence_score": company.confidence_score,
            "source_urls": source_urls,
        }

    def export_leads(
        self, companies: List[Company], *, format: str
    ) -> Tuple[str, str, int]:
        rows = [self._company_row(c) for c in companies]
        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        fmt = format.upper()

        if fmt == "JSON":
            file_name = f"leads_{timestamp}.json"
            file_path = os.path.join(self.export_dir, file_name)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=2, default=str)
        elif fmt == "EXCEL":
            file_name = f"leads_{timestamp}.xlsx"
            file_path = os.path.join(self.export_dir, file_name)
            pd.DataFrame(rows).to_excel(file_path, index=False)
        else:
            file_name = f"leads_{timestamp}.csv"
            file_path = os.path.join(self.export_dir, file_name)
            if rows:
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("")

        return file_name, file_path, len(rows)
