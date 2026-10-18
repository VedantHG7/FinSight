import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from './api'
import { AccountBar, useAuth } from './Accounts'

export function Workspace() {
  const { account } = useAuth()
  const [query, setQuery] = useState(''), [state, setState] = useState(''), [page, setPage] = useState(1)
  const [data, setData] = useState(null), [error, setError] = useState('')
  useEffect(() => {
    let active = true
    const load = async () => { try { const value = await api(`/analysis?q=${encodeURIComponent(query)}&state=${state}&page=${page}`); if (active) {setData(value);setError('')} } catch(err) {if(active)setError(err.message)} }
    const timer = setTimeout(load, 200), poll = setInterval(load, 5000)
    return () => {active = false;clearTimeout(timer);clearInterval(poll)}
  }, [query,state,page])
  return <div className="workspace"><AccountBar/><main className="workspace-main"><div className="page-title"><p className="eyebrow">{account.organization.name}</p><h1>Your client workspace</h1><p>Start an analysis, return to a previous workbook, or continue a finding review.</p></div><div className="workspace-toolbar"><label className="field-grow">Search clients or workbooks<input type="search" value={query} onChange={e=>{setQuery(e.target.value);setPage(1)}} placeholder="Company or filename"/></label><label>Status<select value={state} onChange={e=>{setState(e.target.value);setPage(1)}}><option value="">All statuses</option>{['queued','running','completed','failed','cancelled'].map(s=><option key={s}>{s}</option>)}</select></label>{account.user.role !== 'reviewer' && <Link className="primary-button slim" to="/app/new">New analysis</Link>}</div>{error && <p role="alert" className="error-text">{error}</p>}
    {!data ? <p role="status">Loading client history…</p> : data.items.length ? <><div className="history-list">{data.items.map(item=><article className="history-card" key={item.analysis_id}><div><span className={`badge ${item.job.state}`}>{item.job.state}</span><h2>{item.company}</h2><p>{item.filename}</p><small>{new Date(item.created_at).toLocaleString()} · Analysis #{item.analysis_id}</small></div><div className="history-summary"><strong>{item.overview.years?.join(' · ') || item.job.stage}</strong>{item.job.state === 'running' && <p>{item.job.progress}% · {item.job.cancel_requested ? 'Cancellation requested' : item.job.stage}</p>}<Link className="secondary-button" to={item.job.state==='completed'?`/app/analysis/${item.analysis_id}`:`/app/processing/${item.analysis_id}`}>{item.job.state==='completed'?'Open analysis':'View progress'} →</Link></div></article>)}</div><div className="pagination"><button className="secondary-button" disabled={page===1} onClick={()=>setPage(page-1)}>Previous</button><span>{data.total} analyses · Page {page}</span><button className="secondary-button" disabled={page*20>=data.total} onClick={()=>setPage(page+1)}>Next</button></div></> : <section className="empty"><h2>{query||state?'No matching analyses':'Your first analysis starts here'}</h2><p>{query||state?'Try another search or status.':'Upload a workbook to build your client history. Existing local analyses can be imported by your administrator.'}</p>{account.user.role !== 'reviewer' && <Link className="primary-button slim" to="/app/new">Upload workbook</Link>}</section>}
  </main></div>
}

export function JobPage() {
  const { analysisId } = useParams(), navigate = useNavigate(), { account } = useAuth()
  const [data,setData] = useState(null), [error,setError] = useState(''), [busy,setBusy] = useState(false)
  useEffect(()=>{
    let active=true
    const load=async()=>{try{const d=await api(`/analysis/${analysisId}`);if(!active)return;setData(d);setError('');if(d.job.state==='completed')navigate(`/app/audit-report/${analysisId}`,{replace:true})}catch(e){if(active)setError(e.message)}}
    load();const timer=setInterval(load,2000);return()=>{active=false;clearInterval(timer)}
  },[analysisId,navigate])
  const action=async name=>{setBusy(true);try{await api(`/analysis/${analysisId}/${name}`,{method:'POST'});setData(await api(`/analysis/${analysisId}`));setError('')}catch(e){setError(e.message)}finally{setBusy(false)}}
  const job=data?.job
  return <div className="workspace"><AccountBar/><main className="job-main"><div className="processing-card"><p className="eyebrow">Analysis #{analysisId}</p><h1>{job?.stage || 'Loading status…'}</h1><p className="upload-help">{data?.filename}</p>{job && <><div className="progress" role="progressbar" aria-label="Analysis progress" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}><span style={{width:`${job.progress}%`}}/></div><p>{job.state==='queued'?'Your workbook is saved and waiting for the worker.':job.state==='running'?'You can leave this page. Processing continues in the background.':job.state==='cancelled'?'Processing was cancelled. Your original workbook is retained.':job.error}</p><p className="upload-help">{job.progress}% · Attempt {job.attempts} · Status updates automatically</p>{job.cancel_requested&&job.state==='running'&&<p role="status">Cancellation will take effect at the next processing checkpoint.</p>}</>}{error&&<p role="alert" className="error-text">{error}</p>}<div className="review-actions"><Link className="secondary-button" to="/app">Back to history</Link>{account.user.role!=='reviewer'&&job&&(['queued','running'].includes(job.state)?<button className="secondary-button" disabled={busy||job.cancel_requested} onClick={()=>action('cancel')}>Cancel analysis</button>:['failed','cancelled'].includes(job.state)&&<button className="primary-button slim" disabled={busy} onClick={()=>action('retry')}>Retry analysis</button>)}</div></div></main></div>
}

export function TeamPage(){
 const {account}=useAuth(),[members,setMembers]=useState([]),[error,setError]=useState(''),[link,setLink]=useState(''),[busy,setBusy]=useState(false)
 useEffect(()=>{api('/auth/members').then(setMembers).catch(e=>setError(e.message))},[])
 const invite=async e=>{e.preventDefault();setBusy(true);setError('');setLink('');try{const data=await api('/auth/invitations',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.currentTarget)))});setLink(`${window.location.origin}/register?invite=${data.token}`)}catch(err){setError(err.message)}finally{setBusy(false)}}
 return <div className="workspace"><AccountBar/><main className="workspace-main"><div className="page-title"><p className="eyebrow">Workspace access</p><h1>Your team</h1><p>Analysts upload and investigate. Reviewers approve decisions. Admins manage workspace invitations.</p></div><div className="history-list">{members.map(m=><article className="history-card" key={m.id}><div><h2>{m.name}</h2><p>{m.email}</p></div><span className="badge">{m.role}</span></article>)}</div>{account.user.role==='admin'&&<section className="finding-card"><h2>Invite a team member</h2><p>Create an invitation for a new account. Share the link directly with the intended recipient; it expires in three days.</p><form className="workspace-toolbar" onSubmit={invite}><label className="field-grow">Email<input type="email" name="email" required/></label><label>Role<select name="role"><option value="analyst">Analyst</option><option value="reviewer">Reviewer</option><option value="admin">Admin</option></select></label><button className="primary-button slim" disabled={busy}>Create invitation</button></form>{link&&<label>Invitation link<input readOnly value={link} onFocus={e=>e.target.select()}/></label>}</section>}{error&&<p role="alert" className="error-text">{error}</p>}</main></div>
}
