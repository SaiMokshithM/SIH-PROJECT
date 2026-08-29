import { useState, useRef, useCallback, useEffect } from 'react'
import { useWebSocket } from './useWebSocket'
import { detectImage, startCamera, stopCamera, startVideoProcessing, STREAM_URL } from './api'
import type { WSMessage, InputMode, ImageResult, Detection, AIEvent, AuthorityUser } from './types'
import { AuthorityLoginModal } from './components/AuthorityLoginModal'
import { AuthorityPortal } from './components/AuthorityPortal'

const riskColor = (s: number) =>
  s >= 80 ? '#ff3b5c' : s >= 60 ? '#ff7043' : s >= 40 ? '#ffb444' : s >= 20 ? '#00ff88' : '#3d6080'
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
    <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:13, color:'var(--accent-cyan)', letterSpacing:'0.12em' }}>
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
    <header style={{ background:'linear-gradient(180deg,#030810 0%,#040c18 100%)', borderBottom:'1px solid rgba(56,182,255,0.15)',
      padding:'0 24px', height:60, display:'flex', alignItems:'center', justifyContent:'space-between',
      position:'sticky', top:0, zIndex:200, boxShadow:'0 1px 40px rgba(0,0,0,0.8)' }}>
      <div style={{ display:'flex', alignItems:'center', gap:14 }}>
        <div style={{ width:38,height:38,background:'linear-gradient(135deg,rgba(56,182,255,0.2),rgba(0,229,255,0.1))',
          border:'1px solid rgba(56,182,255,0.3)',borderRadius:10,display:'flex',alignItems:'center',justifyContent:'center',
          fontSize:18,boxShadow:'0 0 20px rgba(56,182,255,0.15)' }}>🛡</div>
        <div>
          <div className="shimmer-text" style={{ fontSize:14, fontWeight:800, letterSpacing:'0.14em' }}>AI BORDER SURVEILLANCE</div>
          <div style={{ fontSize:9, letterSpacing:'0.2em', color:'var(--text-muted)', fontWeight:500 }}>
            COMMAND CENTER · SIH 2026 · REAL-TIME AI ANALYTICS
          </div>
        </div>
        {ok && (
          <div style={{ display:'flex',alignItems:'center',gap:6,marginLeft:8,background:'rgba(0,255,136,0.08)',
            border:'1px solid rgba(0,255,136,0.2)',borderRadius:99,padding:'4px 10px' }}>
            <div className="dot-live"/><span style={{ fontSize:9,fontWeight:700,color:'#00ff88',letterSpacing:'0.15em' }}>LIVE</span>
          </div>
        )}
      </div>

      <div style={{ display:'flex', gap:1 }}>
        {([['SYSTEM',ok?'ONLINE':'OFFLINE',ok],['AI MODEL',msg?.model??'—',!!msg],
          ['CAMERA',cam?'ONLINE':'OFFLINE',cam],['FPS',msg?.fps?`${msg.fps}`:'—',(msg?.fps??0)>0],
          ['STATUS',msg?.processing?'ACTIVE':'IDLE',msg?.processing??false]] as [string,string,boolean][])
          .map(([label,val,isOk]) => (
          <div key={label} style={{ display:'flex',flexDirection:'column',alignItems:'center',padding:'6px 12px',
            borderRight:'1px solid rgba(56,182,255,0.07)' }}>
            <span style={{ fontSize:8,letterSpacing:'0.15em',color:'var(--text-dim)',marginBottom:3,fontWeight:600 }}>{label}</span>
            <div style={{ display:'flex',alignItems:'center',gap:4 }}>
              <div className={isOk?'dot-live':'dot-offline'} style={{ width:5,height:5 }}/>
              <span style={{ fontSize:11,fontWeight:700,color:isOk?'var(--text-primary)':'var(--text-muted)',
                fontFamily:"'JetBrains Mono',monospace" }}>{val}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display:'flex', alignItems:'center', gap:16 }}>
        <button
          onClick={onOpenAuthority}
          style={{
            background: 'linear-gradient(135deg, rgba(255, 180, 68, 0.15), rgba(255, 59, 92, 0.12))',
            border: '1px solid rgba(255, 180, 68, 0.45)',
            color: '#ffb444',
            borderRadius: 8,
            padding: '6px 14px',
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: '0.1em',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            boxShadow: '0 0 16px rgba(255, 180, 68, 0.15)',
          }}
        >
          <span>🏛</span> HIGHER AUTHORITY PORTAL
        </button>

        <div style={{ display:'flex',flexDirection:'column',alignItems:'flex-end',gap:2 }}>
          <LiveClock/>
          <div style={{ fontSize:9,color:'var(--text-dim)',letterSpacing:'0.1em' }}>
            {lastReceived ? `UPDATED ${lastReceived.toLocaleTimeString()}` : 'AWAITING DATA'}
          </div>
        </div>
      </div>
    </header>
  )
}

function Sidebar({ activeTab, setTab }: { activeTab:string; setTab:(t:string)=>void }) {
  const items = [['dashboard','⚡','DASH'],['tracks','🔍','TRACKS'],['events','🚨','EVENTS'],['modules','⚙','MODS']]
  return (
    <aside style={{ width:64,background:'linear-gradient(180deg,#030810,#040c18)',borderRight:'1px solid rgba(56,182,255,0.1)',
      display:'flex',flexDirection:'column',alignItems:'center',padding:'12px 0',gap:4,flexShrink:0 }}>
      {items.map(([id,icon,label]) => {
        const a = activeTab===id
        return (
          <button key={id} onClick={()=>setTab(id)} title={label} style={{ width:48,height:48,border:'none',cursor:'pointer',
            borderRadius:10,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',gap:2,
            background:a?'rgba(56,182,255,0.12)':'transparent',
            boxShadow:a?'0 0 16px rgba(56,182,255,0.1)':'none',
            borderColor:a?'rgba(56,182,255,0.25)':'transparent', borderStyle:'solid', borderWidth:1,
            transition:'all 0.2s',color:a?'var(--accent-blue)':'var(--text-muted)' }}>
            <span style={{ fontSize:18 }}>{icon}</span>
            <span style={{ fontSize:7,fontWeight:700,letterSpacing:'0.04em' }}>{label}</span>
          </button>
        )
      })}
    </aside>
  )
}

function StatCard({ icon,label,value,color,sub }: { icon:string;label:string;value:number|null;color:string;sub?:string }) {
  return (
    <div className="stat-card panel-glow" style={{ flex:1,minWidth:120 }}>
      <div style={{ display:'flex',alignItems:'flex-start',justifyContent:'space-between',marginBottom:12 }}>
        <div style={{ width:34,height:34,borderRadius:9,background:`${color}15`,border:`1px solid ${color}30`,
          display:'flex',alignItems:'center',justifyContent:'center',fontSize:16 }}>{icon}</div>
        <div style={{ width:5,height:5,borderRadius:'50%',background:color,boxShadow:`0 0 8px ${color}`,marginTop:3 }}/>
      </div>
      <div style={{ fontSize:30,fontWeight:800,color,lineHeight:1,marginBottom:4,fontFamily:"'JetBrains Mono',monospace" }}>
        {value===null ? <span style={{ fontSize:18,color:'var(--text-dim)',fontWeight:400 }}>—</span> : value}
      </div>
      <div style={{ fontSize:9,fontWeight:700,letterSpacing:'0.14em',color:'var(--text-muted)',textTransform:'uppercase' }}>{label}</div>
      {sub && <div style={{ fontSize:9,color,marginTop:3,opacity:0.8 }}>{sub}</div>}
    </div>
  )
}

function RiskGauge({ score,level }: { score:number;level:string }) {
  const c = riskColor(score)
  return (
    <div style={{ padding:'16px 18px 14px' }}>
      <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:10 }}>
        <div>
          <div style={{ fontSize:9,letterSpacing:'0.16em',color:'var(--text-muted)',fontWeight:600,marginBottom:2 }}>OPERATIONAL RISK</div>
          <div style={{ fontSize:9,color:'var(--text-dim)' }}>Decaying weighted events per track</div>
        </div>
        <div style={{ textAlign:'right' }}>
          <div style={{ fontSize:36,fontWeight:900,color:c,lineHeight:1,fontFamily:"'JetBrains Mono',monospace",
            textShadow:`0 0 20px ${c}60` }}>{score}</div>
          <div style={{ fontSize:10,fontWeight:800,color:c,letterSpacing:'0.12em' }}>{level}</div>
        </div>
      </div>
      <div className="risk-track"><div className="risk-fill" style={{ width:`${Math.min(100,score)}%` }}/></div>
      <div style={{ display:'flex',justifyContent:'space-between',marginTop:6,fontSize:8,color:'var(--text-dim)',fontWeight:600 }}>
        <span>0</span><span style={{color:'#00ff88'}}>INFO</span><span style={{color:'#ffb444'}}>MED</span>
        <span style={{color:'#ff7043'}}>HIGH</span><span style={{color:'#ff3b5c'}}>CRIT</span><span>100</span>
      </div>
    </div>
  )
}

function LiveFeed({ msg,imageResult,mode }: { msg:WSMessage|null;imageResult:ImageResult|null;mode:InputMode }) {
  const live = msg?.camera_status==='online'
  if (mode==='image' && imageResult) return (
    <div style={{ position:'relative',background:'#000',borderRadius:8,overflow:'hidden' }}>
      <img src={imageResult.annotated_image} style={{ width:'100%',display:'block' }} alt="AI result"/>
      <div className="scanline-overlay"/>
      <div style={{ position:'absolute',top:10,left:10,background:'rgba(0,229,255,0.12)',border:'1px solid rgba(0,229,255,0.3)',
        backdropFilter:'blur(8px)',borderRadius:6,padding:'4px 12px',fontSize:10,fontWeight:700,
        color:'var(--accent-cyan)',letterSpacing:'0.12em' }}>✓ YOLO PROCESSED</div>
    </div>
  )
  return (
    <div style={{ position:'relative',background:'#000',borderRadius:8,overflow:'hidden',minHeight:300 }}>
      <img src={STREAM_URL} style={{ width:'100%',display:'block',minHeight:300,objectFit:'contain' }} alt="Live"/>
      <div className="scanline-overlay"/>
      {['tl','tr','bl','br'].map(c=>(
        <div key={c} style={{ position:'absolute',
          top:c[0]==='t'?8:undefined,bottom:c[0]==='b'?8:undefined,
          left:c[1]==='l'?8:undefined,right:c[1]==='r'?8:undefined,
          width:18,height:18,
          borderTop:c[0]==='t'?`2px solid ${live?'var(--accent-cyan)':'#ff3b5c'}`:undefined,
          borderBottom:c[0]==='b'?`2px solid ${live?'var(--accent-cyan)':'#ff3b5c'}`:undefined,
          borderLeft:c[1]==='l'?`2px solid ${live?'var(--accent-cyan)':'#ff3b5c'}`:undefined,
          borderRight:c[1]==='r'?`2px solid ${live?'var(--accent-cyan)':'#ff3b5c'}`:undefined,
          opacity:0.7 }}/>
      ))}
      <div style={{ position:'absolute',top:10,left:10,display:'flex',alignItems:'center',gap:6,
        background:'rgba(3,8,16,0.78)',backdropFilter:'blur(8px)',
        border:`1px solid ${live?'rgba(0,255,136,0.25)':'rgba(255,59,92,0.25)'}`,
        borderRadius:6,padding:'5px 12px' }}>
        <div className={live?'dot-live':'dot-offline'}/>
        <span style={{ fontSize:10,fontWeight:700,color:live?'#00ff88':'#ff3b5c',
          letterSpacing:'0.1em',fontFamily:"'JetBrains Mono',monospace" }}>
          {live?`LIVE · ${msg?.fps??0} FPS`:'NO SIGNAL'}
        </span>
      </div>
      {!live && (
        <div style={{ position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center',
          background:'rgba(2,4,8,0.85)',flexDirection:'column',gap:10 }}>
          <div style={{ fontSize:40,animation:'float 3s ease infinite' }}>📡</div>
          <div style={{ fontSize:13,fontWeight:700,color:'#ff3b5c',letterSpacing:'0.1em' }}>⚠ CAMERA OFFLINE</div>
          <div style={{ fontSize:10,color:'var(--text-muted)' }}>Start camera or upload a file to begin</div>
        </div>
      )}
      {msg?.is_night && live && (
        <div style={{ position:'absolute',top:10,right:10,background:'rgba(99,102,241,0.15)',
          border:'1px solid rgba(99,102,241,0.3)',borderRadius:6,padding:'4px 10px',
          fontSize:10,fontWeight:700,color:'#a5b4fc',letterSpacing:'0.1em' }}>🌙 NIGHT MODE</div>
      )}
    </div>
  )
}

function DetectionTable({ detections }: { detections:Detection[] }) {
  if (!detections.length) return (
    <div style={{ padding:32,textAlign:'center',color:'var(--text-dim)',fontSize:12 }}>
      <div style={{ fontSize:28,marginBottom:8 }}>🔎</div>
      <div style={{ fontWeight:600,letterSpacing:'0.1em' }}>NO OBJECTS DETECTED</div>
      <div style={{ fontSize:10,marginTop:4 }}>Waiting for AI pipeline detections</div>
    </div>
  )
  return (
    <div style={{ overflowY:'auto',maxHeight:340 }}>
      <table>
        <thead>
          <tr><th>ID</th><th>CLASS</th><th>CONF</th><th>MOVEMENT</th><th>DIR</th><th>ZONE</th><th>RISK</th><th>TIME</th></tr>
        </thead>
        <tbody>
          {detections.map(d=>(
            <tr key={d.track_id}>
              <td><span style={{ fontFamily:"'JetBrains Mono',monospace",color:'var(--accent-blue)',fontWeight:700 }}>
                #{String(d.track_id).padStart(3,'0')}</span></td>
              <td>{catChip(d.category,d.class_name)}</td>
              <td><span style={{ color:d.confidence>=0.75?'#00ff88':d.confidence>=0.5?'#ffb444':'#ff3b5c',
                fontWeight:700,fontFamily:"'JetBrains Mono',monospace" }}>{(d.confidence*100).toFixed(0)}%</span></td>
              <td><span style={{ fontSize:11 }}>{movIcon(d.movement_state)} {d.movement_state}</span></td>
              <td style={{ fontSize:10,color:'var(--text-muted)' }}>{d.direction.replace('_',' ')}</td>
              <td>{d.current_zone?<span className="badge badge-amber">{d.current_zone}</span>:
                <span style={{ color:'var(--text-dim)' }}>—</span>}</td>
              <td>
                <div style={{ display:'flex',alignItems:'center',gap:5 }}>
                  <div style={{ width:28,height:3,borderRadius:99,background:'var(--bg-hover)',overflow:'hidden' }}>
                    <div style={{ width:`${Math.min(100,d.risk_score)}%`,height:'100%',background:riskColor(d.risk_score) }}/>
                  </div>
                  <span style={{ fontSize:10,color:riskColor(d.risk_score),fontWeight:700,fontFamily:"'JetBrains Mono',monospace" }}>
                    {d.risk_score}</span>
                </div>
              </td>
              <td style={{ fontSize:10,color:'var(--text-muted)',fontFamily:"'JetBrains Mono',monospace" }}>{d.time_in_scene}s</td>
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
    <div style={{ padding:32,textAlign:'center',color:'var(--text-dim)',fontSize:12 }}>
      <div style={{ fontSize:28,marginBottom:8 }}>⏳</div>
      <div style={{ fontWeight:600,letterSpacing:'0.1em' }}>NO EVENTS YET</div>
      <div style={{ fontSize:10,marginTop:4 }}>Zone/behavior triggers will appear here</div>
    </div>
  )
  return (
    <div style={{ overflowY:'auto',maxHeight:360,padding:'8px 0' }}>
      {sorted.map((evt,i)=>(
        <div key={evt.event_id} className={`event-item sev-bg-${evt.severity}`}
          style={{ margin:'3px 10px',borderRadius:8,padding:'10px 14px',animationDelay:`${i*0.02}s` }}>
          <div style={{ display:'flex',justifyContent:'space-between',alignItems:'flex-start',gap:8 }}>
            <div style={{ flex:1 }}>
              <div style={{ display:'flex',alignItems:'center',gap:6,flexWrap:'wrap' }}>
                <span className={`sev-${evt.severity}`} style={{ fontWeight:800,fontSize:11,letterSpacing:'0.06em' }}>
                  [{sevEmoji(evt.severity)}] {evt.event_type.replace(/_/g,' ')}
                </span>
                {evt.track_id!=null&&<span className="badge badge-blue">T#{evt.track_id}</span>}
                {evt.object_type&&<span className="badge badge-gray">{evt.object_type}</span>}
              </div>
              {evt.zone_name&&<div style={{ fontSize:10,color:'#ffb444',marginTop:3 }}>Zone: {evt.zone_name}</div>}
              {evt.description&&<div style={{ fontSize:10,color:'var(--text-dim)',marginTop:2 }}>{evt.description}</div>}
            </div>
            <div style={{ textAlign:'right',flexShrink:0 }}>
              <div style={{ fontSize:10,fontFamily:"'JetBrains Mono',monospace",color:'var(--text-muted)' }}>
                {evt.timestamp?.split('T')[1]?.slice(0,8)??''}
              </div>
              {evt.risk_score>0&&<div style={{ fontSize:10,color:riskColor(evt.risk_score),fontWeight:700,marginTop:2 }}>R:{evt.risk_score}</div>}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function ModuleGrid({ msg }: { msg:WSMessage|null }) {
  const ms = msg?.module_status
  const mods = [
    { n:'YOLO Detection', ok:true, d:msg?.model??'yolov8n.pt', i:'🎯' },
    { n:'IoU Tracker', ok:true, d:'Multi-object', i:'🔍' },
    { n:'Movement', ok:true, d:'Speed+Direction', i:'📐' },
    { n:'Zone Manager', ok:true, d:`${ms?.zones??0} zones`, i:'🗺' },
    { n:'Risk Engine', ok:true, d:'0-100 decay', i:'⚠' },
    { n:'Camera Health', ok:true, d:'Freeze detect', i:'📷' },
    { n:'Night Detect', ok:true, d:msg?.is_night?'NIGHT':'Day', i:'🌙' },
    { n:'Face Detect', ok:ms?.face??true, d:'Haar cascade', i:'👤' },
    { n:'ANPR', ok:ms?.anpr??false, d:ms?.anpr?'Active':'Needs easyocr', i:'🔤' },
    { n:'Weapon Detect', ok:ms?.weapon??false, d:ms?.weapon?'Active':'Needs model', i:'🔫' },
  ]
  return (
    <div style={{ display:'grid',gridTemplateColumns:'1fr 1fr',gap:6,padding:'12px 14px' }}>
      {mods.map(m=>(
        <div key={m.n} style={{ display:'flex',alignItems:'center',gap:8,
          background:m.ok?'rgba(0,255,136,0.03)':'rgba(255,59,92,0.03)',
          border:`1px solid ${m.ok?'rgba(0,255,136,0.1)':'rgba(255,59,92,0.1)'}`,
          borderRadius:8,padding:'8px 10px' }}>
          <span style={{ fontSize:14 }}>{m.i}</span>
          <div style={{ flex:1,minWidth:0 }}>
            <div style={{ fontSize:10,fontWeight:700,color:m.ok?'var(--text-primary)':'var(--text-muted)',
              whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis' }}>{m.n}</div>
            <div style={{ fontSize:9,color:'var(--text-dim)',marginTop:1 }}>{m.d}</div>
          </div>
          <div className={m.ok?'dot-live':'dot-offline'} style={{ width:6,height:6,flexShrink:0 }}/>
        </div>
      ))}
    </div>
  )
}

function CameraControls({ mode,setMode,onImage,onVideo,onStart,onStop,running }: {
  mode:InputMode;setMode:(m:InputMode)=>void;onImage:(f:File)=>void;onVideo:(f:File)=>void;
  onStart:()=>void;onStop:()=>void;running:boolean;
}) {
  const imgRef = useRef<HTMLInputElement>(null)
  const vidRef = useRef<HTMLInputElement>(null)
  return (
    <div style={{ padding:'14px 16px',display:'flex',flexDirection:'column',gap:12 }}>
      <div style={{ display:'flex',gap:8 }}>
        {([['live','📡','LIVE'],['image','🖼','IMAGE'],['video','🎬','VIDEO']] as const).map(([id,icon,label])=>(
          <button key={id} className={`mode-btn ${mode===id?'active':''}`} onClick={()=>setMode(id as InputMode)}>
            <span>{icon}</span><span>{label}</span>
          </button>
        ))}
      </div>
      <div style={{ display:'flex',gap:8,alignItems:'center' }}>
        {mode==='live'&&(!running
          ?<button className="btn btn-green" onClick={onStart}>▶ Start Webcam</button>
          :<button className="btn btn-red" onClick={onStop}>⏹ Stop</button>)}
        {mode==='image'&&<>
          <button className="btn btn-default" onClick={()=>imgRef.current?.click()}>📂 Upload Image</button>
          <input ref={imgRef} type="file" accept=".jpg,.jpeg,.png,.bmp" style={{ display:'none' }}
            onChange={e=>e.target.files?.[0]&&onImage(e.target.files[0])}/>
        </>}
        {mode==='video'&&<>
          <button className="btn btn-default" onClick={()=>vidRef.current?.click()}>📂 Upload Video</button>
          <input ref={vidRef} type="file" accept=".mp4,.avi,.mov,.mkv" style={{ display:'none' }}
            onChange={e=>e.target.files?.[0]&&onVideo(e.target.files[0])}/>
        </>}
        <span style={{ fontSize:10,color:'var(--text-dim)' }}>
          {mode==='live'?'cv2.VideoCapture(0) — system webcam':
           mode==='image'?'Real YOLO inference — annotated result returned':
           'Full AI pipeline — MJPEG stream output'}
        </span>
      </div>
    </div>
  )
}

function ImageSummary({ result }: { result:ImageResult }) {
  const counts = result.counts as any
  return (
    <div style={{ padding:'14px 16px' }}>
      <div style={{ display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(80px, 1fr))',gap:8,marginBottom:12 }}>
        {[
          ['PEOPLE', counts.person || 0, 'var(--accent-blue)'],
          ['VEHICLES', counts.vehicle || 0, '#00ff88'],
          ['WEAPONS', counts.weapon || 0, '#ff3b5c'],
          ['PLATES', counts.plate || 0, '#00e5ff'],
          ['ANIMALS', counts.animal || 0, '#ffb444'],
          ['TOTAL', counts.total || result.detections.length, 'var(--accent-cyan)']
        ].map(([l,v,c])=>(
          <div key={String(l)} style={{ background:'var(--bg-card)',border:'1px solid var(--border)',
            borderRadius:8,padding:'10px',textAlign:'center' }}>
            <div style={{ fontSize:20,fontWeight:800,color:String(c),fontFamily:"'JetBrains Mono',monospace" }}>{v}</div>
            <div style={{ fontSize:9,fontWeight:700,color:'var(--text-muted)',letterSpacing:'0.1em' }}>{l}</div>
          </div>
        ))}
      </div>
      <div style={{ display:'flex',flexDirection:'column',gap:4,maxHeight:250,overflowY:'auto' }}>
        {result.detections.map((d,i)=>(
          <div key={i} style={{ display:'flex',gap:10,padding:'7px 0',borderBottom:'1px solid rgba(14,35,60,0.8)',alignItems:'center' }}>
            {catChip(d.category,d.class_name)}
            <span style={{ fontFamily:"'JetBrains Mono',monospace",fontSize:11,
              color:d.confidence>=0.75?'#00ff88':'#ffb444',fontWeight:700 }}>{(d.confidence*100).toFixed(0)}%</span>
            <span style={{ fontSize:10,color:'var(--text-dim)',fontFamily:"'JetBrains Mono',monospace" }}>
              [{d.bbox.join(', ')}]</span>
          </div>
        ))}
      </div>
      {!result.detections.length&&<div style={{ color:'var(--text-dim)',fontSize:12,padding:'12px 0' }}>
        No supported objects detected</div>}
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

  // Authority Portal state
  const [authorityUser, setAuthorityUser] = useState<AuthorityUser | null>(() => {
    try {
      const saved = localStorage.getItem('authority_user')
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })
  const [showAuthModal, setShowAuthModal] = useState(false)
  const [viewMode, setViewMode] = useState<'operator' | 'authority'>('operator')

  const handleOpenAuthority = () => {
    if (authorityUser) {
      setViewMode('authority')
    } else {
      setShowAuthModal(true)
    }
  }

  const handleImage = useCallback(async (file:File)=>{
    setLoading(true);setLoadMsg(`Running YOLO on ${file.name}...`);setError('');setImageResult(null)
    try { setImageResult(await detectImage(file)) } catch(e:any){ setError(e.message) }
    finally { setLoading(false);setLoadMsg('') }
  },[])

  const handleVideo = useCallback(async (file:File)=>{
    setLoading(true);setLoadMsg(`Processing ${file.name}...`);setError('')
    try { await startVideoProcessing(file);setMode('video');setCameraRunning(true) } catch(e:any){ setError(e.message) }
    finally { setLoading(false);setLoadMsg('') }
  },[])

  const handleStart = useCallback(async ()=>{
    setLoading(true);setLoadMsg('Opening webcam...');setError('')
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

  const PH = (text:string) => (
    <div style={{ display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',
      padding:40,color:'var(--text-dim)',gap:8 }}>
      <div style={{ fontSize:9,letterSpacing:'0.18em',fontWeight:700 }}>{text}</div>
    </div>
  )

  if (viewMode === 'authority' && authorityUser) {
    return (
      <AuthorityPortal
        user={authorityUser}
        msg={message}
        wsStatus={wsStatus}
        onExit={() => setViewMode('operator')}
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
            <div style={{ padding:'10px 20px 0',display:'flex',flexDirection:'column',gap:6 }}>
              {wsLost&&<div className="alert-banner alert-danger">⚡ LIVE DATA LOST · Last: {lastReceived?.toLocaleTimeString()??'?'} · Reconnecting...</div>}
              {camLost&&<div className="alert-banner alert-warn">📷 CAMERA OFFLINE · Start a camera or upload a file</div>}
            </div>
          )}
          {/* Loading */}
          {(loading||error)&&(
            <div style={{ padding:'10px 20px 0',display:'flex',gap:8,flexDirection:'column' }}>
              {loading&&<div style={{ background:'rgba(56,182,255,0.06)',border:'1px solid rgba(56,182,255,0.2)',
                borderRadius:8,padding:'10px 16px',fontSize:12,color:'var(--accent-blue)',display:'flex',gap:8,alignItems:'center' }}>
                <div style={{ width:14,height:14,border:'2px solid var(--accent-blue)',borderTopColor:'transparent',
                  borderRadius:'50%',animation:'spin 0.7s linear infinite' }}/>{loadMsg}</div>}
              {error&&<div className="alert-banner alert-danger">{error}</div>}
            </div>
          )}

          {/* DASHBOARD TAB */}
          {activeTab==='dashboard'&&(
            <div style={{ padding:'16px 20px',display:'flex',flexDirection:'column',gap:14 }}>
              {/* Stats */}
              <div style={{ display:'flex',gap:12 }}>
                <StatCard icon="👤" label="People"   value={counts?.person??null}  color="var(--accent-blue)"/>
                <StatCard icon="🚗" label="Vehicles" value={counts?.vehicle??null} color="#00ff88"/>
                <StatCard icon="🐾" label="Animals"  value={counts?.animal??null}  color="#ffb444"/>
                <StatCard icon="🔍" label="Tracked"  value={counts?.tracked??null} color="var(--accent-cyan)"/>
                <StatCard icon="🚨" label="Events"   value={evts.length}           color="#ff7043"
                  sub={evts.length>0?`Latest: ${evts[evts.length-1]?.severity}`:undefined}/>
                <StatCard icon="⚠"  label="Risk"     value={riskScore}             color={riskColor(riskScore)} sub={riskLv}/>
              </div>

              {/* 2-col layout */}
              <div style={{ display:'grid',gridTemplateColumns:'1fr 340px',gap:14 }}>
                <div style={{ display:'flex',flexDirection:'column',gap:14 }}>
                  {/* Input controls */}
                  <div className="panel panel-glow">
                    <div className="panel-header"><div className="panel-header-icon">📡</div>INPUT MODE</div>
                    <CameraControls mode={mode} setMode={(m)=>{setMode(m);if(m!=='image')setImageResult(null)}}
                      onImage={handleImage} onVideo={handleVideo}
                      onStart={handleStart} onStop={handleStop} running={cameraRunning}/>
                  </div>
                  {/* Video */}
                  <div className="panel panel-glow">
                    <div className="panel-header">
                      <div className="panel-header-icon">🎥</div>
                      {mode==='image'?'AI PROCESSED IMAGE':'LIVE AI FEED'}
                      {message?.camera_status==='online'&&mode!=='image'&&(
                        <span className="badge badge-green" style={{ marginLeft:'auto' }}>● RECEIVING</span>
                      )}
                    </div>
                    <div style={{ padding:10 }}><LiveFeed msg={message} imageResult={imageResult} mode={mode}/></div>
                    {mode==='image'&&imageResult&&<><div className="divider"/><ImageSummary result={imageResult}/></>}
                  </div>
                  {/* Table */}
                  <div className="panel panel-glow">
                    <div className="panel-header">
                      <div className="panel-header-icon">📊</div>ACTIVE TRACKED OBJECTS
                      <span style={{ marginLeft:'auto',fontSize:9,color:'var(--text-muted)' }}>
                        {dets.length} OBJECT{dets.length!==1?'S':''}</span>
                    </div>
                    <DetectionTable detections={dets}/>
                  </div>
                </div>

                {/* Right col */}
                <div style={{ display:'flex',flexDirection:'column',gap:14 }}>
                  <div className="panel panel-glow">
                    <div className="panel-header"><div className="panel-header-icon">⚠</div>RISK ENGINE</div>
                    {message?<RiskGauge score={riskScore} level={riskLv}/>:PH('AWAITING BACKEND')}
                  </div>
                  <div className="panel panel-glow" style={{ flex:1 }}>
                    <div className="panel-header">
                      <div className="panel-header-icon">🚨</div>LIVE EVENTS
                      {evts.length>0&&<span style={{ marginLeft:'auto',background:'#7f1d1d',color:'#fca5a5',
                        borderRadius:99,padding:'1px 8px',fontSize:9,fontWeight:800 }}>{evts.length}</span>}
                    </div>
                    <EventsFeed events={evts}/>
                  </div>
                  <div className="panel panel-glow">
                    <div className="panel-header"><div className="panel-header-icon">⚙</div>AI MODULES</div>
                    <ModuleGrid msg={message}/>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab==='tracks'&&(
            <div style={{ padding:'16px 20px' }}>
              <div className="panel panel-glow">
                <div className="panel-header"><div className="panel-header-icon">🔍</div>ALL TRACKED OBJECTS
                  <span style={{ marginLeft:'auto',fontSize:9,color:'var(--text-muted)' }}>{dets.length} TRACKED</span>
                </div>
                <DetectionTable detections={dets}/>
              </div>
            </div>
          )}

          {activeTab==='events'&&(
            <div style={{ padding:'16px 20px' }}>
              <div className="panel panel-glow">
                <div className="panel-header"><div className="panel-header-icon">🚨</div>EVENT FEED
                  {evts.length>0&&<span style={{ marginLeft:'auto',background:'#7f1d1d',color:'#fca5a5',
                    borderRadius:99,padding:'1px 8px',fontSize:9,fontWeight:800 }}>{evts.length}</span>}
                </div>
                <EventsFeed events={evts}/>
              </div>
            </div>
          )}

          {activeTab==='modules'&&(
            <div style={{ padding:'16px 20px',display:'flex',flexDirection:'column',gap:14 }}>
              <div className="panel panel-glow">
                <div className="panel-header"><div className="panel-header-icon">⚙</div>AI MODULE STATUS</div>
                <ModuleGrid msg={message}/>
              </div>
              <div className="panel panel-glow">
                <div className="panel-header"><div className="panel-header-icon">⚠</div>RISK ENGINE</div>
                {message?<RiskGauge score={riskScore} level={riskLv}/>:PH('AWAITING')}
              </div>
            </div>
          )}

          {/* Footer */}
          <div style={{ padding:'10px 24px',borderTop:'1px solid rgba(14,35,60,0.8)',
            display:'flex',justifyContent:'space-between',fontSize:9,
            color:'var(--text-dim)',fontWeight:600,letterSpacing:'0.1em' }}>
            <div>AI BORDER SURVEILLANCE · SIH 2026</div>
            <div>ALL VALUES FROM REAL YOLOv8 AI BACKEND</div>
            <div style={{ color:wsStatus==='connected'?'#00ff88':'#ff3b5c' }}>WS {wsStatus.toUpperCase()}</div>
          </div>
        </main>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}} @keyframes float{0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)}}`}</style>
    </div>
  )
}
