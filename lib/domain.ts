import type { AppState, Assignment, Meeting } from "./types";
export function localDay(date = new Date()): string { return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`; }
export function dateOffset(days: number, now = new Date()): string {const d=new Date(now);d.setDate(d.getDate()+days);return localDay(d)}
export function statusOf(a: Assignment, today = localDay()) {return a.status !== "done" && a.deadline < today ? "overdue" : a.status;}
export function dueSoon(a: Assignment, now=new Date()) { return a.status!=="done" && a.deadline<=dateOffset(3,now); }
export const statusLabels = {new:"Новое",progress:"В работе",done:"Исполнено",overdue:"Просрочено"};
export function protocolErrors(m: Meeting): string[] {
 const p=m.protocol;if(!p)return ["Сначала сформируйте проект протокола."];
 const errors:string[]=[];
 if(!p.themes.trim())errors.push("Укажите основные вопросы обсуждения.");
 if(!p.decisions.trim())errors.push("Укажите принятые решения.");
 p.assignments.forEach((a,i)=>{if([a.text,a.assignee,a.deadline,a.department,a.initiator,a.agenda].some(v=>!v.trim())) errors.push(`Заполните все поля поручения №${i+1}.`);else if(!/^\d{4}-\d{2}-\d{2}$/.test(a.deadline)||Number.isNaN(new Date(a.deadline+"T12:00:00").getTime()))errors.push(`Проверьте срок поручения №${i+1}.`);});
 return errors;
}
export function approveMeeting(state: AppState, id: string, now=new Date()): AppState {
 const m=state.meetings.find(m=>m.id===id);if(!m)throw new Error("Совещание не найдено.");
 if(m.protocol?.approvedAt)return state;
 const errors=protocolErrors(m);if(errors.length)throw new Error(errors.join(" "));
 const p=m.protocol!;
 return {...state,meetings:state.meetings.map(x=>x.id===id?{...x,protocol:{...p,approvedAt:now.toISOString()}}:x),assignments:[...state.assignments,...p.assignments.filter(a=>!state.assignments.some(existing=>existing.id===a.id)).map(a=>({...a,status:"new" as const}))]};
}
export function newAssignment(meeting: Meeting): Assignment {return {id:crypto.randomUUID(),meetingId:meeting.id,text:"",assignee:meeting.participants[0]?.name||"",deadline:dateOffset(7),department:meeting.participants[0]?.department||"",initiator:meeting.participants[0]?.name||"",agenda:meeting.agenda[0]||"",status:"new"};}
