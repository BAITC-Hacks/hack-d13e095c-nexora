"use client";
import { Empty as EmptyPrimitive } from "@/components/ui/empty";

import { Select,SelectContent,SelectItem,SelectTrigger,SelectValue } from "@/components/ui/select";
import { Table,TableBody,TableCell,TableHead,TableHeader,TableRow } from "@/components/ui/table";
import { ArrowUpRight, ListChecks } from "lucide-react";
import { statusLabels,statusOf } from "@/lib/domain";
import type { Assignment,AssignmentStatus } from "@/lib/types";
export function Choice({value,onChange,items,label,disabled=false}:{value:string;onChange:(v:string)=>void;items:[string,string][];label:string;disabled?:boolean}){return <Select value={value} onValueChange={onChange} disabled={disabled}><SelectTrigger aria-label={label} className="choice"><SelectValue/></SelectTrigger><SelectContent>{items.map(([v,t])=><SelectItem key={v} value={v}>{t}</SelectItem>)}</SelectContent></Select>}
export function Badge({status}:{status:string}){const colors:Record<string,string>={new:"blue",progress:"orange",done:"green",overdue:"red",review:"orange",approved:"green",planned:"blue"};const labels:Record<string,string>={...statusLabels,review:"На проверке",approved:"Утверждён",planned:"Запланировано"};return <span className={`badge ${colors[status]||""}`}><i/>{labels[status]||status}</span>}
export function dateText(value:string){return new Date(value.length===10?value+"T12:00:00":value).toLocaleDateString("ru-RU",{day:"numeric",month:"short"})}
export function initials(name:string){return name.split(" ").map(x=>x[0]).slice(0,2).join("")}
export function Empty({title,description}:{title:string;description:string}){return <EmptyPrimitive className="empty-state"><ListChecks size={28}/><h3>{title}</h3><p>{description}</p></EmptyPrimitive>}
export function AssignmentTable({items,onStatus,onMeeting,compact=false}:{items:Assignment[];onStatus:(id:string,status:AssignmentStatus)=>void;onMeeting:(id:string)=>void;compact?:boolean}){return !items.length?<Empty title="Поручений пока нет" description="Они появятся здесь после утверждения протокола."/>:<Table className="assignment-table"><TableHeader><TableRow><TableHead>Поручение</TableHead><TableHead>Ответственный</TableHead><TableHead>Срок</TableHead><TableHead>Статус</TableHead>{!compact&&<TableHead>Изменить статус</TableHead>}</TableRow></TableHeader><TableBody>{items.map(a=><TableRow key={a.id}><TableCell><button className="task-title" onClick={()=>onMeeting(a.meetingId)}>{a.text}<ArrowUpRight size={13}/></button><small>{a.department}</small></TableCell><TableCell><span className="person"><span className="avatar mini">{initials(a.assignee)}</span>{a.assignee}</span></TableCell><TableCell className={statusOf(a)==="overdue"?"overdue":""}>{dateText(a.deadline)}</TableCell><TableCell><Badge status={statusOf(a)}/></TableCell>{!compact&&<TableCell><Choice label={`Статус: ${a.text}`} value={a.status} onChange={v=>onStatus(a.id,v as AssignmentStatus)} items={[["new","Новое"],["progress","В работе"],["done","Исполнено"]]}/></TableCell>}</TableRow>)}</TableBody></Table>}



export function countLabel(n:number,forms:[string,string,string]){const last=n%10;const teen=n%100;return `${n} ${forms[teen>=11&&teen<=14?2:last===1?0:last>=2&&last<=4?1:2]}`;}
