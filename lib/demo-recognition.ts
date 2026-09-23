import type { Meeting, Protocol, TranscriptSegment } from "./types";
import { newAssignment } from "./domain";
// Replace this service with a real transcription API when backend integration is added.
// The demo intentionally does not analyze or upload the recorded audio.
export async function recognizeDemo(meeting:Meeting):Promise<{transcript:TranscriptSegment[];protocol:Protocol}> {
 await new Promise(resolve=>setTimeout(resolve,1000));
 const speaker=meeting.participants[0]?.name||"Секретарь";
 return {transcript:meeting.agenda.map((agenda,i)=>({id:crypto.randomUUID(),speaker:meeting.participants[i%meeting.participants.length]?.name||speaker,time:`${String(i).padStart(2,"0")}:00`,text:`Рассмотрим вопрос «${agenda}». Предлагаю подготовить предложения и согласовать дальнейший план действий.`})),protocol:{themes:meeting.agenda.join("\n"),decisions:"Подготовить предложения по вопросам повестки и согласовать план дальнейших действий. Проверить ответственных и сроки перед утверждением.",assignments:meeting.agenda.map((agenda,i)=>{const person=meeting.participants[i%meeting.participants.length];return {...newAssignment(meeting),agenda,text:`Подготовить предложения по вопросу «${agenda}»`,assignee:person?.name||"",department:person?.department||""}})}};
}
