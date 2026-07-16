import {redirect} from "next/navigation";
export default async function CaseIndex({params}:{params:Promise<{caseId:string}>}){const {caseId}=await params;redirect(`/cases/${caseId}/dashboard`)}
