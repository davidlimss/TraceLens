import AppShell from "@/components/AppShell";
export default async function CaseLayout({children,params}:{children:React.ReactNode;params:Promise<{caseId:string}>}){const {caseId}=await params;return <AppShell caseId={caseId}>{children}</AppShell>}
