export interface Participant { id: string; name: string; department: string }
export interface TranscriptSegment { id: string; speaker: string; time: string; text: string }
export type AssignmentStatus = "new" | "progress" | "done";
export interface Assignment { id: string; meetingId: string; text: string; assignee: string; deadline: string; department: string; initiator: string; agenda: string; status: AssignmentStatus }
export interface Protocol { themes: string; decisions: string; assignments: Assignment[]; approvedAt?: string }
export interface Meeting { id: string; title: string; date: string; participants: Participant[]; agenda: string[]; transcript: TranscriptSegment[]; protocol?: Protocol; audio?: Blob; audioSeconds?: number; demo?: boolean }
export interface AppState { version: 1; meetings: Meeting[]; assignments: Assignment[] }
