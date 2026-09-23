from app.schemas.analysis import MeetingAnalysis


class SummaryService:
    @staticmethod
    def combine(parts: list[MeetingAnalysis]) -> tuple[str, list[str], list[str]]:
        """Combine chronological chunk summaries without another unconstrained generation."""
        summary = "\n\n".join(dict.fromkeys(part.summary for part in parts if part.summary))
        topics = list(dict.fromkeys(topic for part in parts for topic in part.topics))
        decisions = list(
            dict.fromkeys(item.description for part in parts for item in part.decisions)
        )
        return summary, topics, decisions
