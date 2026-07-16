const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
function cookie(name:string):string|undefined{return document.cookie.split("; ").find(item=>item.startsWith(`${name}=`))?.split("=").slice(1).join("=")}
export async function api<T>(path:string, init?:RequestInit):Promise<T>{
  const csrf=typeof document!=="undefined"?cookie("tracelens_csrf"):undefined;
  const response=await fetch(`${API_URL}${path}`,{...init,credentials:"include",headers:{...(init?.body instanceof FormData?{}:{"Content-Type":"application/json"}),...(csrf&&init?.method&&init.method!=="GET"?{"X-CSRF-Token":decodeURIComponent(csrf)}:{}),...init?.headers},cache:"no-store"});
  if(!response.ok){
    const isLoginPage=typeof window!=="undefined"&&window.location.pathname==="/login";
    if(response.status===401&&path!=="/auth/login"&&!isLoginPage&&typeof window!=="undefined")window.location.replace("/login");
    let message=`API error ${response.status}`;try{const body=await response.json();message=body.detail?.message??body.detail??message}catch{}throw new Error(String(message))
  } return (response.status===204?undefined:await response.json()) as T;
}
export function uploadLog(caseId:string,file:File,onProgress:(value:number)=>void,parsingMode:"strict"|"quarantine"="strict"):Promise<unknown>{return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open("POST",`${API_URL}/cases/${caseId}/logs`);xhr.withCredentials=true;const csrf=cookie("tracelens_csrf");if(csrf)xhr.setRequestHeader("X-CSRF-Token",decodeURIComponent(csrf));xhr.upload.onprogress=(event)=>event.lengthComputable&&onProgress(Math.round(event.loaded/event.total*100));xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve(JSON.parse(xhr.responseText)):reject(new Error(JSON.parse(xhr.responseText||"{}").detail?.message||`Upload gagal (${xhr.status})`));xhr.onerror=()=>reject(new Error("Koneksi upload gagal"));const form=new FormData();form.append("file",file);form.append("parsing_mode",parsingMode);xhr.send(form)})}
