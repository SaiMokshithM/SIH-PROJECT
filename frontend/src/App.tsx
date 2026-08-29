import { useState, useRef, useCallback, useEffect } from 'react'
import { useWebSocket } from './useWebSocket'
import { detectImage, startCamera, stopCamera, startVideoProcessing, STREAM_URL } from './api'
import type { WSMessage, InputMode, ImageResult, Detection, AIEvent, AuthorityUser } from './types'
import { AuthorityLoginModal } from './components/AuthorityLoginModal'
import { AuthorityPortal } from './components/AuthorityPortal'

const riskColor = (s: number) =>
  s >= 80 ? '#EF4444' : s >= 60 ? '#F97316' : s >= 40 ? '#F59E0B' : s >= 20 ? '#10B981' : '#64748B'
const riskLabel = (s: number) =>
  s >= 80 ? 'CRITICAL' : s >= 60 ? 'HIGH' : s >= 40 ? 'MEDIUM' : s >= 20 ? 'LOW' : 'INFO'
const sevEmoji = (s: string) =>
  ({ CRITICAL: 'CRIT', HIGH: 'HIGH', MEDIUM: 'MED', LOW: 'LOW', INFO: 'INFO' } as any)[s] ?? ''
const movIcon = (s: string) =>
  ({ FAST: 'FAST', NORMAL: 'MOVE', SLOW: 'SLOW', VERY_SLOW: 'VSLOW', STATIONARY: 'STILL', UNKNOWN: '?' } as any)[s] ?? '?'
const catChip = (cat: string, name: string) => {
  const cls = cat === 'person' ? 'chip-person' : cat === 'vehicle' ? 'chip-vehicle' : 'chip-animal'
  return <span className={cls}>{name}</span>
}

function LiveClock() {
  const [t, setT] = useState(new Date())
  useEffect(() => { const id = setInterval(() => setT(new Date()), 1000); return () => clearInterval(id) }, [])
  return (
    <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:12, color:'var(--text-secondary)', letterSpacing:'0.08em', fontWeight: 600 }}>
      {t.toLocaleTimeString('en-GB', { hour12:false })}
    </span>
  )
}

function Header({
  msg,
  wsStatus,
  lastReceived,
  onOpenAuthority,
}: {
  msg: WSMessage|null;
  wsStatus:string;
  lastReceived:Date|null;
  onOpenAuthority: () => void;
}) {
  const ok = wsStatus==='connected', cam = msg?.camera_status==='online'
  return (
    <header style={{ background:'var(--bg-surface)', borderBottom:'1px solid var(--border)',
      padding:'0 20px', height:56, display:'flex', alignItems:'center', justifyContent:'space-between',
      position:'sticky', top:0, zIndex:200 }}>
      <div style={{ display:'flex', alignItems:'center', gap:12 }}>
        <div style={{ width:34,height:34,background:'var(--bg-card)',
          border:'1px solid var(--border)',borderRadius:6,display:'flex',alignItems:'center',justifyContent:'center',
          fontSize:16 }}>🛡</div>
        <div>
          <div style={{ fontSize:13, fontWeight:800, letterSpacing:'0.06em', color: '#F8FAFC' }}>
            BORDER SURVEILLANCE COMMAND CENTER
          </div>
          <div style={{ fontSize:9, letterSpacing:'0.08em', color:'var(--text-muted)', fontWeight:600 }}>
            TACTICAL AI PERIMETER ANALYTICS · BSF / ITBP SPEC · SIH 2026
          </div>
        </div>
        {ok && (
          <div style={{ display:'flex',alignItems:'center',gap:5,marginLeft:6,background:'rgba(16,185,129,0.1)',
            border:'1px solid rgba(16,185,129,0.25)',borderRadius:4,padding:'3px 8px' }}>
            <div className="dot-live"/><span style={{ fontSize:9,fontWeight:800,color:'#10B981',letterSpacing:'0.08em' }}>FEED LIVE</span>
          </div>
        )}
      </div>

      <div style={{ display:'flex', gap:2 }}>
        {([['SYSTEM',ok?'ONLINE':'OFFLINE',ok],['MODEL',msg?.model??'YOLOv8',!!msg],
          ['CAMERA',cam?'ONLINE':'OFFLINE',cam],['FPS',msg?.fps?`${msg.fps}`:'—',(msg?.fps??0)>0],
          ['PIPELINE',msg?.processing?'ACTIVE':'IDLE',msg?.processing??false]] as [string,string,boolean][])
          .map(([label,val,isOk]) => (
          <div key={label} style={{ display:'flex',flexDirection:'column',alignItems:'center',padding:'4px 10px',
            borderRight:'1px solid var(--border)' }}>
            <span style={{ fontSize:8,letterSpacing:'0.08em',color:'var(--text-dim)',marginBottom:2,fontWeight:700 }}>{label}</span>
            <div style={{ display:'flex',alignItems:'center',gap:4 }}>
              <div className={isOk?'dot-live':'dot-offline'} style={{ width:5,height:5 }}/>
              <span style={{ fontSize:10,fontWeight:700,color:isOk?'var(--text-primary)':'var(--text-muted)',
                fontFamily:"'JetBrains Mono',monospace" }}>{val}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display:'flex', alignItems:'center', gap:14 }}>
        <button
          onClick={onOpenAuthority}
          style={{
            background: 'rgba(217, 119, 6, 0.12)',
            border: '1px solid rgba(217, 119, 6, 0.4)',
            color: '#FBBF24',
            borderRadius: 6,
            padding: '6px 12px',
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: '0.06em',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <span>🏛</span> HIGHER AUTHORITY PORTAL
        </button>

        <div style={{ display:'flex',flexDirection:'column',alignItems:'flex-end',gap:1 }}>
          <LiveClock/>
          <div style={{ fontSize:9,color:'var(--text-dim)',letterSpacing:'0.06em' }}>
            {lastReceived ? `UPDATED ${lastReceived.toLocaleTimeString()}` : 'AWAITING DATA'}
          </div>
        </div>
      </div>
    </header>
  )
}

function Sidebar({ activeTab, setTab }: { activeTab:string; setTab:(t:string)=>void }) {
  const items = [['dashboard','⚡','DASH'],['tracks','🔍','TRACKS'],['events','🚨','EVENTS'],['modules','⚙','SUBSYS']]
  return (
    <aside style={{ width:60,background:'var(--bg-surface)',borderRight:'1px solid var(--border)',
      display:'flex',flexDirection:'column',alignItems:'center',padding:'12px 0',gap:4,flexShrink:0 }}>
      {items.map(([id,icon,label]) => {
        const a = activeTab===id
        return (
          <button key={id} onClick={()=>setTab(id)} title={label} style={{ width:44,height:44,border:'none',cursor:'pointer',
            borderRadius:6,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',gap:2,
            background:a?'#1E293B':'transparent',
            borderColor:a?'var(--border-light)':'transparent', borderStyle:'solid', borderWidth:1,
            transition:'all 0.15s',color:a?'#3B82F6':'var(--text-muted)' }}>
            <span style={{ fontSize:15 }}>{icon}</span>
            <span style={{ fontSize:7,fontWeight:800,letterSpacing:'0.04em' }}>{label}</span>
          </button>
        )
      })}
    </aside>
  )
}

function StatCard({ icon,label,value,color,sub }: { icon:string;label:string;value:number|null;color:string;sub?:string }) {
  return (
    <div className="stat-card" style={{ flex:1,minWidth:110 }}>
      <div style={{ display:'flex',alignItems:'flex-start',justifyContent:'space-between',marginBottom:8 }}>
        <div style={{ width:28,height:28,borderRadius:6,background:`${color}15`,border:`1px solid ${color}30`,
          display:'flex',alignItems:'center',justifyContent:'center',fontSize:13 }}>{icon}</div>
        <div style={{ width:5,height:5,borderRadius:'50%',background:color,marginTop:3 }}/>
      </div>
      <div style={{ fontSize:24,fontWeight:800,color,lineHeight:1,marginBottom:3,fontFamily:"'JetBrains Mono',monospace" }}>
        {value===null ? <span style={{ fontSize:16,color:'var(--text-dim)',fontWeight:400 }}>—</span> : value}
      </div>
      <div style={{ fontSize:9,fontWeight:700,letterSpacing:'0.08em',color:'var(--text-muted)',textTransform:'uppercase' }}>{label}</div>
      {sub && <div style={{ fontSize:9,color,marginTop:2,opacity:0.9 }}>{sub}</div>}
    </div>
  )
}

function RiskGauge({ score,level }: { score:number;level:string }) {
  const c = riskColor(score)
  return (
    <div style={{ padding:'14px 16px' }}>
      <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:8 }}>
        <div>
          <div style={{ fontSize:9,letterSpacing:'0.1em',color:'var(--text-muted)',fontWeight:700,marginBottom:2 }}>OPERATIONAL RISK LEVEL</div>
          <div style={{ fontSize:9,color:'var(--text-dim)' }}>Calculated priority threat score</div>
        </div>
        <div style={{ textAlign:'right' }}>
          <div style={{ fontSize:28,fontWeight:900,color:c,lineHeight:1,fontFamily:"'JetBrains Mono',monospace" }}>{score}</div>
          <div style={{ fontSize:9,fontWeight:800,color:c,letterSpacing:'0.08em' }}>{level}</div>
        </div>
      </div>
      <div style={{ height:5, background:'rgba(255,255,255,0.06)', borderRadius:4, overflow:'hidden' }}>
        <div style={{ height:'100%', width:`${Math.min(100,score)}%`, background:c, transition:'width 0.4s ease' }}/>
      </div>
      <div style={{ display:'flex',justifyContent:'space-between',marginTop:5,fontSize:8,color:'var(--text-dim)',fontWeight:700 }}>
        <span>0</span><span style={{color:'#10B981'}}>LOW (20)</span><span style={{color:'#F59E0B'}}>MED (50)</span>
        <span style={{color:'#EF4444'}}>CRIT (90)</span><span>100</span>
      </div>
    </div>
  )
}

function LiveFeed({ msg,imageResult,mode }: { msg:WSMessage|null;imageResult:ImageResult|null;mode:InputMode }) {
  const live = msg?.camera_status==='online'
  if (mode==='image' && imageResult) return (
    <div style={{ position:'relative',background:'#000',borderRadius:6,overflow:'hidden' }}>
      <img src={imageResult.annotated_image} style={{ width:'100%',display:'block' }} alt="AI result"/>
      <div className="scanline-overlay"/>
      <div style={{ position:'absolute',top:10,left:10,background:'rgba(15,23,42,0.85)',border:'1px solid var(--border-light)',
        borderRadius:4,padding:'3px 10px',fontSize:9,fontWeight:700,color:'#93C5FD',letterSpacing:'0.08em' }}>
        ✓ FORENSIC SCAN COMPLETE
      </div>
    </div>
  )
  return (
    <div style={{ position:'relative',background:'#000',borderRadius:6,overflow:'hidden',minHeight:300 }}>
      <img src={STREAM_URL} style={{ width:'100%',display:'block',minHeight:300,objectFit:'contain' }} alt="Live"/>
      <div className="scanline-overlay"/>
      {['tl','tr','bl','br'].map(c=>(
        <div key={c} style={{ position:'absolute',
          top:c[0]==='t'?6:undefined,bottom:c[0]==='b'?6:undefined,
          left:c[1]==='l'?6:undefined,right:c[1]==='r'?6:undefined,
          width:14,height:14,
          borderTop:c[0]==='t'?`1.5px solid ${live?'#3B82F6':'#EF4444'}`:undefined,
          borderBottom:c[0]==='b'?`1.5px solid ${live?'#3B82F6':'#EF4444'}`:undefined,
          borderLeft:c[1]==='l'?`1.5px solid ${live?'#3B82F6':'#EF4444'}`:undefined,
          borderRight:c[1]==='r'?`1.5px solid ${live?'#3B82F6':'#EF4444'}`:undefined,
          opacity:0.6 }}/>
      ))}
      <div style={{ position:'absolute',top:10,left:10,display:'flex',alignItems:'center',gap:6,
        background:'rgba(12,16,26,0.88)',
        border:`1px solid ${live?'rgba(16,185,129,0.3)':'rgba(239,68,68,0.3)'}`,
        borderRadius:4,padding:'4px 10px' }}>
        <div className={live?'dot-live':'dot-offline'}/>
        <span style={{ fontSize:9,fontWeight:800,color:live?'#10B981':'#EF4444',
          letterSpacing:'0.08em',fontFamily:"'JetBrains Mono',monospace" }}>
          {live?`CHANNEL 01 · ${msg?.fps??0} FPS`:'NO SIGNAL'}
        </span>
      </div>
      {!live && (
        <div style={{ position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center',
          background:'rgba(8,12,20,0.88)',flexDirection:'column',gap:8 }}>
          <div style={{ fontSize:32 }}>📡</div>
          <div style={{ fontSize:12,fontWeight:800,color:'#EF4444',letterSpacing:'0.08em' }}>CAMERA STANDBY</div>
          <div style={{ fontSize:10,color:'var(--text-muted)' }}>Click 'Start Webcam' or upload imagery to analyze</div>
        </div>
      )}
      {msg?.is_night && live && (
        <div style={{ position:'absolute',top:10,right:10,background:'rgba(30,41,59,0.9)',
          border:'1px solid var(--border-light)',borderRadius:4,padding:'3px 8px',
          fontSize:9,fontWeight:800,color:'#CBD5E1',letterSpacing:'0.08em' }}>🌙 NIGHT FILTER ACTIVE</div>
      )}
    </div>
  )
}

function DetectionTable({ detections }: { detections:Detection[] }) {
  if (!detections.length) return (
    <div style={{ padding:28,textAlign:'center',color:'var(--text-dim)',fontSize:11 }}>
      <div style={{ fontSize:24,marginBottom:6 }}>🔎</div>
      <div style={{ fontWeight:700,letterSpacing:'0.08em' }}>NO TARGETS IN SCENE</div>
      <div style={{ fontSize:9,marginTop:3 }}>AI tracker awaiting object detection</div>
    </div>
  )
  return (
    <div style={{ overflowY:'auto',maxHeight:340 }}>
      <table>
        <thead>
          <tr><th>TRACK ID</th><th>CLASS</th><th>CONF</th><th>MOTION</th><th>DIR</th><th>ZONE</th><th>RISK</th><th>TIME</th></tr>
        </thead>
        <tbody>
          {detections.map(d=>(
            <tr key={d.track_id}>
              <td><span style={{ fontFamily:"'JetBrains Mono',monospace",color:'#3B82F6',fontWeight:700 }}>
                #{String(d.track_id).padStart(3,'0')}</span></td>
              <td>{catChip(d.category,d.class_name)}</td>
              <td><span style={{ color:d.confidence>=0.75?'#10B981':d.confidence>=0.5?'#F59E0B':'#EF4444',
                fontWeight:700,fontFamily:"'JetBrains Mono',monospace" }}>{(d.confidence*100).toFixed(0)}%</span></td>
              <td><span style={{ fontSize:10 }}>{movIcon(d.movement_state)} {d.movement_state}</span></td>
              <td style={{ fontSize:9,color:'var(--text-muted)' }}>{d.direction.replace('_',' ')}</td>
              <td>{d.current_zone?<span className="badge badge-amber">{d.current_zone}</span>:
                <span style={{ color:'var(--text-dim)' }}>—</span>}</td>
              <td>
                <span style={{ fontSize:10,color:riskColor(d.risk_score),fontWeight:800,fontFamily:"'JetBrains Mono',monospace" }}>
                  {d.risk_score}
                </span>
              </td>
              <td style={{ fontSize:9,color:'var(--text-muted)',fontFamily:"'JetBrains Mono',monospace" }}>{d.time_in_scene}s</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EventsFeed({ events }: { events:AIEvent[] }) {
  const sorted = [...events].reverse()
  if (!sorted.length) return (
    <div style={{ padding:28,textAlign:'center',color:'var(--text-dim)',fontSize:11 }}>
      <div style={{ fontSize:24,marginBottom:6 }}>⏳</div>
      <div style={{ fontWeight:700,letterSpacing:'0.08em' }}>NO RECENT EVENTS</div>
      <div style={{ fontSize:9,marginTop:3 }}>Perimeter breach and threat events will log here</div>
    </div>
  )
  return (
    <div style={{ overflowY:'auto',maxHeight:360,padding:'6px 0' }}>
      {sorted.map((evt)=>(
        <div key={evt.event_id} className={`event-item sev-bg-${evt.severity}`}
          style={{ margin:'2px 8px',borderRadius:6,padding:'8px 12px' }}>
          <div style={{ display:'flex',justifyContent:'space-between',alignItems:'flex-start',gap:8 }}>
            <div style={{ flex:1 }}>
              <div style={{ display:'flex',alignItems:'center',gap:6,flexWrap:'wrap' }}>
                <span className={`sev-${evt.severity}`} style={{ fontWeight:800,fontSize:10,letterSpacing:'0.04em' }}>
                  [{sevEmoji(evt.severity)}] {evt.event_type.replace(/_/g,' ')}
                </span>
                {evt.track_id!=null&&<span className="badge badge-blue">T#{evt.track_id}</span>}
                {evt.object_type&&<span className="badge badge-gray">{evt.object_type}</span>}
              </div>
              {evt.zone_name&&<div style={{ fontSize:9,color:'#F59E0B',marginTop:2 }}>Zone: {evt.zone_name}</div>}
              {evt.description&&<div style={{ fontSize:9,color:'var(--text-secondary)',marginTop:2 }}>{evt.description}</div>}
            </div>
            <span style={{ fontSize:8,color:'var(--text-muted)',fontFamily:"'JetBrains Mono',monospace",flexShrink:0 }}>
              {evt.timestamp.slice(11,19)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

function ModulesPanel({ msg }: { msg:WSMessage|null }) {
  const mods = [
    { label:'YOLO DETECTOR', on:true, desc:msg?.model??'yolov8n.pt' },
    { label:'WEAPON DETECTION', on:msg?.module_status?.weapon??false, desc:'Firearm Model active' },
    { label:'ANPR ENGINE', on:msg?.module_status?.anpr??false, desc:'License Plate OCR' },
    { label:'FACE DETECTOR', on:msg?.module_status?.face??true, desc:'Haar / Face tracker' },
    { label:'ZONE ENGINE', on:(msg?.module_status?.zones??0)>0, desc:`${msg?.module_status?.zones??0} boundary sectors` },
    { label:'RISK CALCULATOR', on:true, desc:'Operational matrix' },
  ]
  return (
    <div style={{ padding:12,display:'grid',gridTemplateColumns:'1fr 1fr',gap:8 }}>
      {mods.map(m=>(
        <div key={m.label} style={{ background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:6,padding:'10px 12px' }}>
          <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:4 }}>
            <span style={{ fontSize:10,fontWeight:800,color:'#F8FAFC' }}>{m.label}</span>
            <span className={m.on?'badge badge-green':'badge badge-gray'}>{m.on?'ACTIVE':'OFFLINE'}</span>
          </div>
          <div style={{ fontSize:9,color:'var(--text-muted)' }}>{m.desc}</div>
        </div>
      ))}
    </div>
  )
}

function ImageUploadPanel({ onUpload }: { onUpload:(f:File)=>void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  return (
    <div style={{ padding:14 }}>
      <div
        onDragOver={e=>{ e.preventDefault(); setDrag(true) }}
        onDragLeave={()=>setDrag(false)}
        onDrop={e=>{ e.preventDefault(); setDrag(false); const f=e.dataTransfer.files[0]; if(f) onUpload(f) }}
        onClick={()=>ref.current?.click()}
        style={{ border:`1.5px dashed ${drag?'#3B82F6':'var(--border-light)'}`,borderRadius:6,
          padding:24,textAlign:'center',cursor:'pointer',background:drag?'rgba(59,130,246,0.06)':'transparent' }}>
        <div style={{ fontSize:28,marginBottom:6 }}>📤</div>
        <div style={{ fontSize:11,fontWeight:700,color:'#F8FAFC' }}>UPLOAD SURVEILLANCE IMAGE</div>
        <div style={{ fontSize:9,color:'var(--text-muted)',marginTop:3 }}>Drop JPG, PNG file to run Weapons, Plate & Object detection</div>
        <input ref={ref} type="file" accept="image/*" style={{ display:'none' }} onChange={e=>{ const f=e.target.files?.[0]; if(f) onUpload(f) }}/>
      </div>
    </div>
  )
}

function VideoUploadPanel({ onUpload }: { onUpload:(f:File)=>void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  return (
    <div style={{ padding:14 }}>
      <div
        onDragOver={e=>{ e.preventDefault(); setDrag(true) }}
        onDragLeave={()=>setDrag(false)}
        onDrop={e=>{ e.preventDefault(); setDrag(false); const f=e.dataTransfer.files[0]; if(f) onUpload(f) }}
        onClick={()=>ref.current?.click()}
        style={{ border:`1.5px dashed ${drag?'#3B82F6':'var(--border-light)'}`,borderRadius:6,
          padding:24,textAlign:'center',cursor:'pointer',background:drag?'rgba(59,130,246,0.06)':'transparent' }}>
        <div style={{ fontSize:28,marginBottom:6 }}>🎞</div>
        <div style={{ fontSize:11,fontWeight:700,color:'#F8FAFC' }}>UPLOAD SURVEILLANCE VIDEO</div>
        <div style={{ fontSize:9,color:'var(--text-muted)',marginTop:3 }}>Drop MP4, AVI video file to run continuous border analytics</div>
        <input ref={ref} type="file" accept="video/*" style={{ display:'none' }} onChange={e=>{ const f=e.target.files?.[0]; if(f) onUpload(f) }}/>
      </div>
    </div>
  )
}

function ImageResultsList({ result }: { result:ImageResult }) {
  return (
    <div style={{ padding:14 }}>
      <div style={{ fontSize:10,fontWeight:700,color:'var(--text-muted)',letterSpacing:'0.08em',marginBottom:8 }}>
        ANALYSIS RESULTS ({result.detections.length} DETECTIONS)
      </div>
      <div style={{ maxHeight:200,overflowY:'auto' }}>
        {result.detections.map((d,i)=>(
          <div key={i} style={{ display:'flex',gap:8,padding:'6px 0',borderBottom:'1px solid var(--border)',alignItems:'center' }}>
            {catChip(d.category,d.class_name)}
            <span style={{ fontFamily:"'JetBrains Mono',monospace",fontSize:10,
              color:d.confidence>=0.75?'#10B981':'#F59E0B',fontWeight:700 }}>{(d.confidence*100).toFixed(0)}%</span>
            <span style={{ fontSize:9,color:'var(--text-dim)',fontFamily:"'JetBrains Mono',monospace" }}>
              [{d.bbox.join(', ')}]</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const { message, wsStatus, lastReceived } = useWebSocket()
  const [activeTab, setActiveTab] = useState('dashboard')
  const [mode, setMode] = useState<InputMode>('live')
  const [imageResult, setImageResult] = useState<ImageResult|null>(null)
  const [cameraRunning, setCameraRunning] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadMsg, setLoadMsg] = useState('')
  const [error, setError] = useState('')

  // Authority Portal state - Always requires PIN clearance
  const [authorityUser, setAuthorityUser] = useState<AuthorityUser | null>(null)
  const [showAuthModal, setShowAuthModal] = useState(false)
  const [viewMode, setViewMode] = useState<'operator' | 'authority'>('operator')

  const handleOpenAuthority = () => {
    setShowAuthModal(true)
  }

  const handleExitAuthority = () => {
    setAuthorityUser(null)
    setViewMode('operator')
    localStorage.removeItem('authority_user')
    localStorage.removeItem('authority_token')
  }

  const handleImage = useCallback(async (file:File)=>{
    setLoading(true);setLoadMsg(`Running detection on ${file.name}...`);setError('');setImageResult(null)
    try { setImageResult(await detectImage(file)) } catch(e:any){ setError(e.message) }
    finally { setLoading(false);setLoadMsg('') }
  },[])

  const handleVideo = useCallback(async (file:File)=>{
    setLoading(true);setLoadMsg(`Processing ${file.name}...`);setError('')
    try { await startVideoProcessing(file);setMode('video');setCameraRunning(true) } catch(e:any){ setError(e.message) }
    finally { setLoading(false);setLoadMsg('') }
  },[])

  const handleStart = useCallback(async ()=>{
    setLoading(true);setLoadMsg('Connecting to video source...');setError('')
    try { await startCamera('0');setCameraRunning(true) } catch(e:any){ setError(e.message) }
    finally { setLoading(false);setLoadMsg('') }
  },[])

  const handleStop = useCallback(async ()=>{ await stopCamera();setCameraRunning(false) },[])

  const dets = message?.detections ?? []
  const evts = message?.events ?? []
  const counts = imageResult?.counts ?? message?.counts
  const riskScore = message?.risk_score ?? 0
  const riskLv = message?.risk_level ?? riskLabel(riskScore)
  const wsLost = wsStatus==='disconnected'||wsStatus==='error'
  const camLost = message?.camera_status==='offline'&&wsStatus==='connected'

  if (viewMode === 'authority' && authorityUser) {
    return (
      <AuthorityPortal
        user={authorityUser}
        msg={message}
        wsStatus={wsStatus}
        onExit={handleExitAuthority}
      />
    )
  }

  return (
    <div style={{ display:'flex',flexDirection:'column',height:'100vh',background:'var(--bg-void)',overflow:'hidden' }}>
      <Header
        msg={message}
        wsStatus={wsStatus}
        lastReceived={lastReceived}
        onOpenAuthority={handleOpenAuthority}
      />
      <AuthorityLoginModal
        isOpen={showAuthModal}
        onClose={() => setShowAuthModal(false)}
        onSuccess={(u) => {
          setAuthorityUser(u)
          setViewMode('authority')
        }}
      />

      <div style={{ display:'flex',flex:1,overflow:'hidden' }}>
        <Sidebar activeTab={activeTab} setTab={setActiveTab}/>

        <main style={{ flex:1,overflowY:'auto',background:'var(--bg-base)' }}>
          {/* Alerts */}
          {(wsLost||camLost)&&(
            <div style={{ padding:'8px 16px 0',display:'flex',flexDirection:'column',gap:6 }}>
              {wsLost&&<div className="alert-banner alert-danger">⚡ TELEMETRY LINK DISCONNECTED · Reconnecting to server...</div>}
              {camLost&&<div className="alert-banner alert-warn">📷 CAMERA STANDBY · Start live camera or upload a file</div>}
            </div>
          )}
          {/* Loading */}
          {(loading||error)&&(
            <div style={{ padding:'8px 16px 0' }}>
              {loading&&<div className="alert-banner" style={{ background:'rgba(59,130,246,0.1)',border:'1px solid rgba(59,130,246,0.3)',color:'#93C5FD' }}>
                ⏳ {loadMsg}</div>}
              {error&&<div className="alert-banner alert-danger">⚠ {error}</div>}
            </div>
          )}

          {/* ════ TAB: DASHBOARD ════ */}
          {activeTab==='dashboard'&&(
            <div style={{ padding:16,display:'flex',flexDirection:'column',gap:14 }}>
              {/* Stat Cards */}
              <div style={{ display:'flex',gap:10,flexWrap:'wrap' }}>
                <StatCard icon="🎯" label="Total Targets" value={counts?.total??0} color="#3B82F6" sub={`${counts?.tracked??0} tracked`}/>
                <StatCard icon="👤" label="Personnel" value={counts?.person??0} color="#60A5FA"/>
                <StatCard icon="🚗" label="Vehicles" value={counts?.vehicle??0} color="#34D399"/>
                <StatCard icon="🔫" label="Firearms" value={counts?.weapon??0} color={(counts?.weapon??0)>0?'#EF4444':'#64748B'} sub={(counts?.weapon??0)>0?'THREAT DETECTED':'Clear'}/>
                <StatCard icon="🔢" label="Number Plates" value={counts?.plate??0} color="#FBBF24"/>
                <StatCard icon="🚨" label="Incidents" value={evts.length} color={evts.length>0?'#F87171':'#64748B'}/>
              </div>

              {/* Main Grid: Left Video / Right Telemetry */}
              <div style={{ display:'grid',gridTemplateColumns:'1fr 340px',gap:14 }}>
                {/* Left: Feed & Mode */}
                <div style={{ display:'flex',flexDirection:'column',gap:10 }}>
                  <div className="panel panel-glow">
                    {/* Header + Mode Switcher */}
                    <div style={{ padding:'8px 12px',display:'flex',justifyContent:'space-between',alignItems:'center',borderBottom:'1px solid var(--border)' }}>
                      <div style={{ display:'flex',gap:6 }}>
                        {(['live','image','video'] as InputMode[]).map(m=>(
                          <button key={m} className={`mode-btn ${mode===m?'active':''}`} onClick={()=>setMode(m)}>
                            {m==='live'?'📹 LIVE FEED':m==='image'?'📷 IMAGE ANALYST':'🎞 VIDEO FORENSICS'}
                          </button>
                        ))}
                      </div>
                      <div style={{ display:'flex',gap:6 }}>
                        {mode==='live'&&(
                          !cameraRunning?(
                            <button className="btn btn-green" onClick={handleStart}>▶ START WEBCAM</button>
                          ):(
                            <button className="btn btn-red" onClick={handleStop}>⏹ STOP</button>
                          )
                        )}
                      </div>
                    </div>

                    <div style={{ padding:10 }}>
                      <LiveFeed msg={message} imageResult={imageResult} mode={mode}/>
                    </div>

                    {mode==='image'&&<ImageUploadPanel onUpload={handleImage}/>}
                    {mode==='image'&&imageResult&&<ImageResultsList result={imageResult}/>}
                    {mode==='video'&&<VideoUploadPanel onUpload={handleVideo}/>}
                  </div>

                  {/* Detection Table */}
                  <div className="panel panel-glow">
                    <div className="panel-header">
                      <div className="panel-header-icon">🔎</div>
                      ACTIVE TARGET TRACKS ({dets.length})
                    </div>
                    <DetectionTable detections={dets}/>
                  </div>
                </div>

                {/* Right: Risk Engine & Real-time Feeds */}
                <div style={{ display:'flex',flexDirection:'column',gap:10 }}>
                  <div className="panel panel-glow">
                    <div className="panel-header">
                      <div className="panel-header-icon">⚡</div>
                      PERIMETER THREAT ASSESSMENT
                    </div>
                    <RiskGauge score={riskScore} level={riskLv}/>
                  </div>

                  <div className="panel panel-glow" style={{ flex:1 }}>
                    <div className="panel-header">
                      <div className="panel-header-icon">🚨</div>
                      REAL-TIME EVENT LOG ({evts.length})
                    </div>
                    <EventsFeed events={evts}/>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ════ TAB: TRACKS ════ */}
          {activeTab==='tracks'&&(
            <div style={{ padding:16 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">🔍</div>
                  FULL TARGET TRACKING MATRIX
                </div>
                <DetectionTable detections={dets}/>
              </div>
            </div>
          )}

          {/* ════ TAB: EVENTS ════ */}
          {activeTab==='events'&&(
            <div style={{ padding:16 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">🚨</div>
                  SECURITY INCIDENT & BREACH TIMELINE
                </div>
                <EventsFeed events={evts}/>
              </div>
            </div>
          )}

          {/* ════ TAB: MODULES ════ */}
          {activeTab==='modules'&&(
            <div style={{ padding:16 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">⚙</div>
                  AI SUBSYSTEMS STATUS
                </div>
                <ModulesPanel msg={message}/>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
