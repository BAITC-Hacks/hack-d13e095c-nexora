from collections import defaultdict

from app.schemas.transcript import DiarizationSegment, MergedSegment, SpeechSegment


class TranscriptMergeService:
    def merge(
        self, speech: list[SpeechSegment], turns: list[DiarizationSegment]
    ) -> list[MergedSegment]:
        """Sum the union of temporal overlaps per speaker, with deterministic ties.

        Adjacent words with the same speaker become readable utterances (<= 30 seconds).
        Overlapping intervals for the same speaker never double count their duration.
        """
        sorted_turns = sorted(turns, key=lambda turn: turn.start)
        cursor = 0
        active = []
        result: list[MergedSegment] = []
        for segment in sorted(speech, key=lambda item: item.start):
            while cursor < len(sorted_turns) and sorted_turns[cursor].start < segment.end:
                active.append(sorted_turns[cursor])
                cursor += 1
            active = [turn for turn in active if turn.end > segment.start]
            overlaps = defaultdict(list)
            for turn in active:
                start, end = max(segment.start, turn.start), min(segment.end, turn.end)
                if end > start:
                    overlaps[turn.speaker].append((start, end))
            scores = {}
            for speaker, intervals in overlaps.items():
                previous_end, total = -1.0, 0.0
                for start, end in sorted(intervals):
                    total += max(0, end - max(start, previous_end))
                    previous_end = max(previous_end, end)
                scores[speaker] = total
            speaker = min(scores, key=lambda key: (-scores[key], key)) if scores else "UNKNOWN"
            if (
                result
                and result[-1].speaker_id == speaker
                and 0 <= segment.start - result[-1].end <= 0.8
                and segment.end - result[-1].start <= 30
            ):
                previous = result[-1]
                previous.end = segment.end
                previous.text += " " + segment.text
            else:
                result.append(MergedSegment(**segment.model_dump(), speaker_id=speaker))
        return result
