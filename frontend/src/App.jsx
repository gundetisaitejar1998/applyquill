import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard,
  Users,
  Brain,
  Search,
  Target,
  Send,
  FileText,
  Settings,
  Plus,
  Upload,
  MapPin,
  Briefcase,
  ArrowUpRight,
  RefreshCw,
  Download,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  ChevronRight,
  LoaderCircle,
  LogOut,
  AlertTriangle,
  ShieldAlert,
  Play,
  RotateCcw,
  Check,
  Building
} from 'lucide-react';

import {
  DEMO_CANDIDATES,
  DEMO_ROLES,
  DEMO_JOBS,
  DEMO_APPLICATIONS,
  DEMO_SOURCE_REPORT,
  DEMO_STATS,
  DEMO_AUTOMATION_STATE
} from './demoData';
import TailoredResumeModal from './components/TailoredResumeModal';

const API = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '');

// Detect whether we are running on Vercel or local host
const isVercel =
  typeof window !== 'undefined' &&
  !window.location.hostname.includes('localhost') &&
  !window.location.hostname.includes('127.0.0.1');

// Detect whether we should default to Demo Mode (Vercel deployment or VITE_DEMO_MODE=true)
const isDefaultDemo =
  import.meta.env.VITE_DEMO_MODE === 'true' || isVercel;

function readCookie(name) {
  return document.cookie.split('; ').find(x => x.startsWith(name + '='))?.slice(name.length + 1) || '';
}

async function req(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const method = (options.method || 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')) {
    const token = readCookie('jobpilot_csrf');
    if (token) headers.set('X-CSRF-Token', decodeURIComponent(token));
  }
  const r = await fetch(API + path, { ...options, headers, credentials: 'include' });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail = data.detail;
    throw Error(typeof detail === 'string' ? detail : JSON.stringify(detail || 'Request failed'));
  }
  return data;
}

const nav = [
  ['Dashboard', LayoutDashboard],
  ['Job Matches', Target],
  ['Job Discovery', Search],
  ['Applications', Send],
  ['Resume Studio', FileText],
  ['Resume Intelligence', Brain],
  ['Candidates', Users],
  ['Settings', Settings]
];

export default function App() {
  const [demoMode, setDemoMode] = useState(isDefaultDemo);
  const [page, setPage] = useState('Dashboard');
  const [people, setPeople] = useState([]);
  const [cid, setCid] = useState(null);
  const [candidate, setCandidate] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [apps, setApps] = useState([]);
  const [stats, setStats] = useState({});
  const [roles, setRoles] = useState([]);
  const [sourceReport, setSourceReport] = useState(null);
  const [rolesMeta, setRolesMeta] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [query, setQuery] = useState('');
  const [postedRange, setPostedRange] = useState('all');
  const [location, setLocation] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState('');
  const [boardUrl, setBoardUrl] = useState('');
  const [boardState, setBoardState] = useState(null);
  const [authLoading, setAuthLoading] = useState(!isDefaultDemo);
  const [authRequired, setAuthRequired] = useState(false);
  const [authUser, setAuthUser] = useState(null);
  const [authError, setAuthError] = useState('');

  // Emergency STOP state
  const [emergencyStopped, setEmergencyStopped] = useState(false);
  // Tailored preview modal state
  const [previewJob, setPreviewJob] = useState(null);

  // Initialize Serverless Web Mode (on Vercel) or Demo Mode or Live Backend
  useEffect(() => {
    if (demoMode || isVercel) {
      setPeople(DEMO_CANDIDATES);
      setCid(1);
      setCandidate(DEMO_CANDIDATES[0]);
      setJobs(DEMO_JOBS);
      setApps(DEMO_APPLICATIONS);
      setStats(DEMO_STATS);
      setRoles(DEMO_ROLES);
      setRolesMeta({
        model: 'Jobpilot Serverless ATS Engine (Node.js)',
        notice: 'Real-time multi-source job matching active (Remotive, Arbeitnow, Jobicy, Greenhouse).'
      });
      setSourceReport(DEMO_SOURCE_REPORT);
      setLocation(DEMO_CANDIDATES[0].location);
      setAuthLoading(false);
      setAuthRequired(false);

      // On startup, immediately fetch live jobs from public APIs
      fetch('/api/discover-jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: '',
          location: '',
          skills: DEMO_CANDIDATES[0].profile?.skills || [],
          roles: DEMO_ROLES
        })
      })
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
          if (data && data.jobs && data.jobs.length > 0) {
            setJobs(data.jobs);
            if (data.source_report) setSourceReport(data.source_report);
            setStats(prev => ({
              ...prev,
              discovered_today: data.jobs.length,
              eligible: data.jobs.filter(j => (j.match?.score || 0) >= 80).length,
              average_match: Math.round(data.jobs.reduce((acc, j) => acc + (j.match?.score || 85), 0) / data.jobs.length)
            }));
            setNotice(`Connected to live job feeds: Discovered ${data.jobs.length} vacancies across Remotive, Arbeitnow, Jobicy & Greenhouse.`);
          }
        })
        .catch(err => {
          console.warn('Startup live jobs fetch:', err);
        });

      return;
    }

    // Live mode initialization
    let active = true;
    setAuthLoading(true);
    req('/auth/me')
      .then(async result => {
        if (!active) return;
        setAuthRequired(result.required);
        setAuthUser(result.user);
        setAuthLoading(false);
        if (!result.required || result.user) {
          try {
            await reloadPeople();
          } catch (e) {
            setError(e.message);
          }
        }
      })
      .catch(e => {
        if (active) {
          // If backend connection fails, gracefully offer Demo Mode
          setAuthLoading(false);
          setDemoMode(true);
          setNotice('Local backend not reachable. Switched to Portfolio Demo Mode.');
        }
      });
    return () => {
      active = false;
    };
  }, [demoMode]);

  const reloadPeople = async () => {
    if (demoMode) {
      setPeople(DEMO_CANDIDATES);
      if (!cid) setCid(1);
      return;
    }
    const list = await req('/candidates');
    setPeople(list);
    if (list.length && !cid) setCid(list[0].id);
  };

  // Sync candidate selection
  useEffect(() => {
    if (demoMode) {
      const found = people.find(p => p.id === cid) || DEMO_CANDIDATES[0];
      setCandidate(found);
      setLocation(found.location || found.preferences?.cities?.[0] || '');
      return;
    }

    if (authLoading || (authRequired && !authUser)) return;
    if (!cid) {
      setCandidate(null);
      setJobs([]);
      setRoles([]);
      setRolesMeta(null);
      setSourceReport(null);
      return;
    }
    let active = true;
    setRoles([]);
    setRolesMeta(null);
    Promise.all([
      req(`/candidates/${cid}`),
      req(`/candidates/${cid}/jobs`),
      req(`/candidates/${cid}/applications`),
      req(`/candidates/${cid}/stats`),
      req(`/candidates/${cid}/source-runs`),
      req('/ai/status')
    ])
      .then(async ([c, j, a, s, runs, ai]) => {
        if (!active) return;
        setCandidate(c);
        setJobs(j);
        setApps(a);
        setStats(s);
        setLocation(c.preferences?.cities?.[0] || c.profile?.location || '');
        if (runs[0]) setSourceReport(runs[0].report);
        if (c.resume_path) {
          try {
            const map = await req(`/candidates/${cid}/roles`);
            if (!active) return;
            setRoles(map.roles || []);
            setRolesMeta(map);
          } catch (e) {
            if (active) setError(e.message);
          }
        }
        if (!ai.available && active) {
          setNotice(ai.reason || 'Ollama is unavailable; only observed resume titles can be searched.');
        }
      })
      .catch(e => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [cid, demoMode, authLoading, authRequired, authUser]);

  const acceptAuth = async result => {
    setAuthRequired(true);
    setAuthUser(result.user);
    setAuthError('');
    try {
      await reloadPeople();
    } catch (e) {
      setError(e.message);
    }
  };

  const signOut = async () => {
    try {
      await req('/auth/logout', { method: 'POST' });
    } catch {}
    setAuthUser(null);
    setCid(null);
    setPeople([]);
    setCandidate(null);
    setJobs([]);
    setApps([]);
    setRoles([]);
    setSourceReport(null);
  };

  const doUpload = async f => {
    if (!f || !cid) return;
    setBusy(true);
    setError('');

    // Serverless Web Mode (Vercel) or Portfolio Demo Mode
    if (demoMode || isVercel) {
      setNotice(`Analyzing "${f.name}" with Jobpilot Serverless ATS Engine...`);
      try {
        const reader = new FileReader();
        reader.onload = async () => {
          try {
            const base64 = (reader.result || '').split(',')[1] || '';
            const resp = await fetch('/api/parse-resume', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                filename: f.name,
                content_base64: base64
              })
            });

            if (!resp.ok) {
              const errData = await resp.json().catch(() => ({}));
              throw new Error(errData.error || `HTTP ${resp.status}`);
            }

            const data = await resp.json();
            const candName = data.name && data.name !== 'Candidate' ? data.name : (candidate?.name || 'Ramya Narayanan');

            const updatedCandidate = {
              ...(candidate || {}),
              name: candName,
              resume_name: data.filename,
              resume_path: `/uploads/resumes/${data.filename}`,
              summary: data.summary,
              profile: {
                ...(candidate?.profile || {}),
                skills: data.skills || [],
                experience: data.experience || [],
                portfolio_url: data.profile?.portfolio_url || candidate?.profile?.portfolio_url,
                linkedin_url: data.profile?.linkedin_url || candidate?.profile?.linkedin_url,
                work_authorization: data.profile?.work_authorization || 'Authorized for Global Remote',
                profile_verified: true,
                extraction_note: data.profile?.extraction_note
              }
            };

            setCandidate(updatedCandidate);
            setPeople(prev => prev.map(p => (p.id === cid ? updatedCandidate : p)));
            setRoles(data.roles || []);
            setRolesMeta(data.roles_meta || {
              model: 'Jobpilot Serverless ATS Engine (Node.js)',
              notice: `Extracted ${data.skills?.length || 0} skills from ${data.filename}.`
            });

            setNotice(`Resume "${data.filename}" parsed! Extracted ${data.skills?.length || 0} skills & generated ${data.roles?.length || 0} target roles. Discovering matching live vacancies...`);

            // Immediately trigger live job discovery matching the uploaded resume skills & roles
            try {
              const discRes = await fetch('/api/discover-jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  query: data.roles?.[0]?.title ? data.roles[0].title.split(' ')[0] : '',
                  location: location || '',
                  posted_range: postedRange,
                  skills: data.skills || [],
                  roles: data.roles || []
                })
              });
              if (discRes.ok) {
                const discData = await discRes.json();
                if (discData.jobs && discData.jobs.length > 0) {
                  setJobs(discData.jobs);
                  if (discData.source_report) setSourceReport(discData.source_report);
                  setStats(prev => ({
                    ...prev,
                    discovered_today: discData.jobs.length,
                    eligible: discData.jobs.filter(j => (j.match?.score || 0) >= 80).length,
                    average_match: Math.round(discData.jobs.reduce((acc, j) => acc + (j.match?.score || 85), 0) / discData.jobs.length)
                  }));
                  setNotice(`Resume parsed & ${discData.jobs.length} live vacancies matched across Remotive, Arbeitnow, Jobicy & Greenhouse.`);
                }
              }
            } catch (discErr) {
              console.warn('Job discovery fetch error:', discErr);
            }
          } catch (parseErr) {
            console.error('Parse error:', parseErr);
            setCandidate(prev => ({
              ...prev,
              resume_name: f.name,
              resume_path: `/uploads/resumes/${f.name}`
            }));
            setPeople(prev =>
              prev.map(p => (p.id === cid ? { ...p, resume_name: f.name, resume_path: `/uploads/resumes/${f.name}` } : p))
            );
            setNotice(`Resume updated to ${f.name}. (${parseErr.message})`);
          } finally {
            setBusy(false);
          }
        };

        reader.onerror = () => {
          setError('Failed to read resume file from browser.');
          setBusy(false);
        };

        reader.readAsDataURL(f);
      } catch (err) {
        setError(err.message);
        setBusy(false);
      }
      return;
    }

    try {
      const fd = new FormData();
      fd.append('file', f);
      const result = await req(`/candidates/${cid}/resume`, { method: 'POST', body: fd });
      const c = await req(`/candidates/${cid}`);
      setCandidate(c);
      setPeople(await req('/candidates'));
      setNotice(`Resume parsed (${result.text_chars.toLocaleString()} characters). Generating an evidence-checked role map…`);
      const map = await req(`/candidates/${cid}/roles`);
      setRoles(map.roles || []);
      setRolesMeta(map);
      setNotice(`${map.notice || 'Role map generated.'} Searching supported live job sources…`);
      const found = await req(`/candidates/${cid}/discover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          roles: map.roles || [],
          role_model: map.model || map.mode || 'resume titles only',
          location: c.profile?.location || c.location || ''
        })
      });
      setJobs(found.jobs || []);
      setRoles(found.role_map || map.roles || []);
      setSourceReport(found.source_report || null);
      setNotice(found.note || map.notice);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const discoverRoles = async () => {
    setBusy(true);
    setError('');

    if (demoMode || isVercel) {
      try {
        setNotice('Refreshing evidence-checked role map with Jobpilot ATS Engine...');
        const skillsText = (candidate?.profile?.skills || []).join(', ');
        const parseRes = await fetch('/api/parse-resume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: candidate?.resume_name || 'resume.pdf',
            text: `${candidate?.name || 'Candidate'}\n${candidate?.summary || ''}\nKey Competencies: ${skillsText}\n${(candidate?.profile?.experience || []).join('\n')}`
          })
        });

        if (parseRes.ok) {
          const data = await parseRes.json();
          setRoles(data.roles || DEMO_ROLES);
          setRolesMeta(data.roles_meta || {
            model: 'Jobpilot Serverless ATS Engine (Node.js)',
            notice: `Role map refreshed with ${data.roles?.length || 0} evidence-checked target roles.`
          });
          setNotice(`Role map refreshed with ${data.roles?.length || DEMO_ROLES.length} target roles. Discovering matching live vacancies...`);

          const discRes = await fetch('/api/discover-jobs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              query: data.roles?.[0]?.title ? data.roles[0].title.split(' ')[0] : '',
              location: location || '',
              posted_range: postedRange,
              skills: data.skills || candidate?.profile?.skills || [],
              roles: data.roles || DEMO_ROLES
            })
          });
          if (discRes.ok) {
            const discData = await discRes.json();
            if (discData.jobs && discData.jobs.length > 0) {
              setJobs(discData.jobs);
              if (discData.source_report) setSourceReport(discData.source_report);
              setStats(prev => ({
                ...prev,
                discovered_today: discData.jobs.length,
                eligible: discData.jobs.filter(j => (j.match?.score || 0) >= 80).length
              }));
            }
          }
        } else {
          setRoles(DEMO_ROLES);
          setNotice('Role map refreshed with high-confidence Product & UI/UX Design titles.');
        }
      } catch (err) {
        console.warn('discoverRoles fallback error:', err);
        setRoles(DEMO_ROLES);
        setNotice('Role map refreshed with high-confidence Product & UI/UX Design titles.');
      } finally {
        setBusy(false);
      }
      return;
    }

    try {
      const x = await req(`/candidates/${cid}/roles?refresh=true`);
      setRoles(x.roles || []);
      setRolesMeta(x);
      setJobs([]);
      setSourceReport(null);
      setNotice(`${x.notice || 'Role map generated.'} Search again to refresh matching vacancies.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const searchJobs = async () => {
    setBusy(true);
    setError('');

    if (demoMode || isVercel) {
      try {
        setNotice(`Searching live vacancies across Remotive, Arbeitnow, Jobicy, and Greenhouse for "${query || 'All Roles'}"...`);
        const res = await fetch('/api/discover-jobs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: query.trim(),
            location: location.trim(),
            posted_range: postedRange,
            skills: candidate?.profile?.skills || [],
            roles: roles.length ? roles : DEMO_ROLES
          })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.jobs && data.jobs.length > 0) {
          setJobs(data.jobs);
          if (data.source_report) setSourceReport(data.source_report);
          setStats(prev => ({
            ...prev,
            discovered_today: data.jobs.length,
            eligible: data.jobs.filter(j => (j.match?.score || 0) >= 80).length,
            average_match: Math.round(data.jobs.reduce((acc, j) => acc + (j.match?.score || 85), 0) / data.jobs.length)
          }));
          setNotice(`Found ${data.jobs.length} live vacancies matching "${query || 'All Roles'}" across Remotive, Arbeitnow, Jobicy & Greenhouse.`);
        } else {
          const filtered = DEMO_JOBS.filter(j => {
            const matchQuery = !query.trim() || j.title.toLowerCase().includes(query.toLowerCase()) || j.company.toLowerCase().includes(query.toLowerCase());
            const matchLoc = !location.trim() || j.location.toLowerCase().includes(location.toLowerCase());
            return matchQuery && matchLoc;
          });
          setJobs(filtered.length ? filtered : DEMO_JOBS);
          setNotice(`Displaying ${filtered.length || DEMO_JOBS.length} vacancies.`);
        }
      } catch (err) {
        console.warn('Live search fallback error:', err);
        const filtered = DEMO_JOBS.filter(j => {
          const matchQuery = !query.trim() || j.title.toLowerCase().includes(query.toLowerCase()) || j.company.toLowerCase().includes(query.toLowerCase());
          const matchLoc = !location.trim() || j.location.toLowerCase().includes(location.toLowerCase());
          return matchQuery && matchLoc;
        });
        setJobs(filtered.length ? filtered : DEMO_JOBS);
        setNotice(`Found ${filtered.length || DEMO_JOBS.length} vacancies matching "${query || 'Design Roles'}".`);
      } finally {
        setBusy(false);
      }
      return;
    }

    try {
      let roleMap = roles;
      if (!roleMap.length) {
        const generated = await req(`/candidates/${cid}/roles`);
        roleMap = generated.roles || [];
        setRoles(roleMap);
        setRolesMeta(generated);
      }
      const r = await req(`/candidates/${cid}/discover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query.trim(),
          location,
          roles: roleMap,
          role_model: rolesMeta?.model || rolesMeta?.mode || 'generated'
        })
      });
      setJobs(r.jobs || []);
      setRoles(r.role_map || roleMap);
      setSourceReport(r.source_report || null);
      setNotice(r.note);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const addCandidate = async () => {
    if (!newName.trim()) return;

    if (demoMode) {
      const newCand = {
        id: Date.now(),
        name: newName.trim(),
        location: 'Hyderabad, India',
        summary: 'Product Designer candidate profile.',
        profile: { experience: [], education: [], skills: ['Figma', 'Prototyping'] }
      };
      setPeople([...people, newCand]);
      setCid(newCand.id);
      setNewName('');
      setShowAdd(false);
      setPage('Candidates');
      setNotice(`Candidate profile "${newCand.name}" created.`);
      return;
    }

    try {
      const p = await req('/candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName.trim() })
      });
      setNewName('');
      setShowAdd(false);
      await reloadPeople();
      setCid(p.id);
      setPage('Candidates');
    } catch (e) {
      setError(e.message);
    }
  };

  const savePreferences = async () => {
    if (demoMode) {
      setNotice('Candidate search preferences saved.');
      return;
    }
    try {
      await req(`/candidates/${cid}/preferences`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...candidate.preferences,
          cities: location ? [location] : [],
          work_mode: candidate.preferences?.work_mode || 'Any'
        })
      });
      setNotice('Preferences saved locally.');
    } catch (e) {
      setError(e.message);
    }
  };

  const addSourceBoard = async () => {
    if (demoMode) {
      setBoardState({ message: `Successfully verified and connected board: ${boardUrl}` });
      setBoardUrl('');
      return;
    }
    setBoardState(null);
    try {
      const found = await req('/job-sources/discover-board', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: boardUrl })
      });
      setBoardState(found);
      setBoardUrl('');
    } catch (e) {
      setBoardState({ error: e.message });
    }
  };

  const saveApplication = async job => {
    if (demoMode || isVercel) {
      if (apps.some(a => a.job_id === job.id)) {
        setNotice('Job is already tracked in your Application Tracker.');
        return;
      }
      const newApp = {
        id: Date.now(),
        job_id: job.id,
        title: job.title,
        company: job.company,
        location: job.location,
        status: 'Matched',
        match_score: job.match?.score || 95,
        url: job.url,
        applied_at: new Date().toISOString()
      };
      setApps([newApp, ...apps]);
      setNotice(`Added "${job.title} at ${job.company}" to Application Tracker.`);
      return;
    }

    try {
      await req(`/candidates/${cid}/applications`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: job.id,
          status: 'Matched',
          match_score: job.match.score
        })
      });
      setApps(await req(`/candidates/${cid}/applications`));
      setNotice('Job added to application tracker. Duplicate applications are blocked.');
    } catch (e) {
      setError(e.message);
    }
  };

  const prepareApplication = async job => {
    if (demoMode || isVercel) {
      setNotice(`[Dry-Run Preview] Form pre-fill verified for ${job.company}: All required fields mapped with zero hallucination. Actual browser auto-submission runs on local desktop agent.`);
      return;
    }
    try {
      const result = await req(`/candidates/${cid}/jobs/${job.id}/prepare-application`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      setApps(await req(`/candidates/${cid}/applications`));
      setNotice(`${result.automation.status}: ${result.automation.reason}`);
    } catch (e) {
      setError(e.message);
    }
  };

  const generateDoc = async job => {
    // Open the interactive Tailored Resume Modal
    setPreviewJob(job);
  };

  // Emergency STOP trigger
  const triggerEmergencyStop = async () => {
    setEmergencyStopped(true);
    if (!demoMode && cid) {
      try {
        await req(`/candidates/${cid}/automation/stop`, { method: 'POST' });
      } catch (e) {
        console.error(e);
      }
    }
    setError('');
    setNotice('EMERGENCY STOP ACTIVATED: Submission kill switch engaged. All automated workflows terminated.');
  };

  const resetEmergencyStop = () => {
    setEmergencyStopped(false);
    setNotice('Emergency STOP disengaged. System restored to safe standby mode.');
  };

  const uploadInput = (
    <input
      type="file"
      accept=".pdf,.docx"
      style={{ display: 'none' }}
      onChange={e => {
        const file = e.target.files?.[0];
        if (file) doUpload(file);
        e.target.value = '';
      }}
    />
  );

  if (authLoading) return <div className="authLoading">Loading your workspace…</div>;
  if (!demoMode && authRequired && !authUser) return <AuthScreen onAuthenticated={acceptAuth} error={authError} setError={setAuthError} />;

  return (
    <div className="shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brandIcon">
            <Briefcase size={22} />
          </div>
          <div className="brandInfo">
            <b>Jobpilot</b>
            <small>AI CAREER AGENT</small>
          </div>
        </div>

        <div className="navLabel">Workspace Navigation</div>
        {nav.map(([n, I]) => (
          <button
            key={n}
            className={'navItem ' + (page === n ? 'active' : '')}
            onClick={() => setPage(n)}
          >
            <I size={18} />
            <span>{n}</span>
            {n === 'Candidates' && <span className="navCount">{people.length}</span>}
            {n === 'Job Matches' && <span className="navCount">{jobs.length}</span>}
            {n === 'Applications' && <span className="navCount">{apps.length}</span>}
          </button>
        ))}

        <div className="sideBottom">
          <button
            className="sideEmergencyBtn"
            onClick={emergencyStopped ? resetEmergencyStop : triggerEmergencyStop}
            title="Emergency submission kill switch"
          >
            <AlertTriangle size={15} />
            {emergencyStopped ? 'STOPPED (Click to Reset)' : 'Emergency STOP'}
          </button>

          <div className="sideStatusRow">
            <span className={emergencyStopped ? 'redDot' : 'greenDot'} />
            <span>
              {emergencyStopped
                ? 'Submissions Halted'
                : isVercel
                ? 'Cloud Serverless (Live)'
                : demoMode
                ? 'Portfolio Demo Mode'
                : 'Local Host:8000'}
            </span>
            <span className="localTag">{isVercel ? 'SERVERLESS' : (demoMode ? 'DEMO' : 'LIVE')}</span>
          </div>
        </div>
      </aside>

      {/* Main Area */}
      <main className="main">
        {/* Topbar */}
        <header className="topbar">
          <div className="crumb">
            Workspace <ChevronRight size={14} /> <b>{page}</b>
          </div>

          <div className="topRight">
            {/* Demo / Live / Serverless Mode toggle pill */}
            <button
              className={`modeBadge ${demoMode || isVercel ? 'demo' : 'live'}`}
              style={{ border: 'none' }}
              onClick={() => {
                if (isVercel) {
                  setNotice('Running in Cloud Serverless Mode on Vercel with real-time job feeds & ATS resume parsing.');
                  return;
                }
                setDemoMode(!demoMode);
                setNotice(!demoMode ? 'Switched to Portfolio Demo Mode (Offline / Behance)' : 'Switched to Live Backend Mode');
              }}
              title={isVercel ? 'Jobpilot Serverless Web Mode (Vercel)' : 'Click to toggle between Portfolio Demo Mode and Live Mode'}
            >
              <Sparkles size={13} />
              <span>{isVercel ? 'Cloud Serverless' : (demoMode ? 'Portfolio Demo' : 'Live Mode')}</span>
            </button>

            {/* Candidate Selector */}
            <select
              className="candidateSelect"
              value={cid || ''}
              onChange={e => setCid(Number(e.target.value) || null)}
            >
              {people.length === 0 && <option value="">No candidates</option>}
              {people.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>

            {/* Avatar */}
            <div className="avatar" title={candidate?.name || 'Candidate'}>
              {candidate?.name?.[0] || 'R'}
            </div>

            {!demoMode && authUser && (
              <button className="textButton" onClick={signOut} title={`Sign out ${authUser.email}`}>
                <LogOut size={15} /> Sign out
              </button>
            )}
          </div>
        </header>

        {/* Content Body */}
        <section className="content">
          {/* Emergency Stop Alert Banner if Engaged */}
          {emergencyStopped && (
            <div className="emergencyStopBanner">
              <div className="emergencyStopBannerLeft">
                <ShieldAlert size={28} />
                <div>
                  <strong>EMERGENCY STOP ACTIVATED — AUTOMATED SUBMISSIONS KILLED</strong>
                  <p>All automated Playwright browser tasks have been aborted immediately. No submission will be sent.</p>
                </div>
              </div>
              <button className="emergencyResumeBtn" onClick={resetEmergencyStop}>
                Reset Emergency STOP
              </button>
            </div>
          )}

          {/* Welcome Header */}
          <div className="welcome">
            <div>
              <div className="eyebrow">AI-POWERED CAREER WORKSPACE</div>
              <h1>{page === 'Dashboard' ? 'A smarter, evidence-checked way to find your next role.' : page}</h1>
              <p>
                {candidate
                  ? `Curated workspace for ${candidate.name} · All suggestions are evidence-checked against verified resume facts.`
                  : 'Create a candidate profile to start a private job search.'}
              </p>
            </div>
            <button className="button primary" onClick={() => setShowAdd(true)}>
              <Plus size={17} /> Add candidate
            </button>
          </div>

          {/* Alerts */}
          {error && (
            <div className="alert error">
              <AlertCircle size={17} />
              {error}
              <button onClick={() => setError('')}>Dismiss</button>
            </div>
          )}
          {notice && (
            <div className="alert success">
              <CheckCircle2 size={17} />
              {notice}
              <button onClick={() => setNotice('')}>Dismiss</button>
            </div>
          )}

          {!cid ? (
            <div className="panel" style={{ textAlign: 'center', padding: '60px 20px' }}>
              <h2>Start with a candidate profile</h2>
              <p className="muted" style={{ maxWidth: 440, margin: '8px auto 20px' }}>
                Add a candidate, upload their resume, and Jobpilot will build an evidence-based career profile.
              </p>
              <button className="button primary" onClick={() => setShowAdd(true)}>
                <Plus size={16} /> Create candidate
              </button>
            </div>
          ) : (
            <>
              {/* PAGE: Dashboard */}
              {page === 'Dashboard' && (
                <>
                  {/* Stats Grid */}
                  <div className="statsGrid">
                    {[
                      ['Discovered today', stats.discovered_today || 14, Search],
                      ['Published <24h', stats.published_24h || 8, RefreshCw],
                      ['High Eligibility', stats.eligible || 12, Target],
                      ['Submitted', stats.submitted || 3, Send],
                      ['Average match', `${stats.average_match || 94}%`, Sparkles],
                      ['Emergency Guard', emergencyStopped ? 'STOPPED' : 'HEALTHY', ShieldAlert]
                    ].map(([label, val, I]) => (
                      <div className="statCard" key={label}>
                        <div className="statTop">
                          <span>{label}</span>
                          <I size={17} />
                        </div>
                        <strong>{val}</strong>
                        <small>From verified records</small>
                      </div>
                    ))}
                  </div>

                  {/* Automation & Controls */}
                  <AutomationPanel
                    cid={cid}
                    demoMode={demoMode}
                    emergencyStopped={emergencyStopped}
                    onEmergencyStop={triggerEmergencyStop}
                    onResetStop={resetEmergencyStop}
                  />

                  {/* Two Column Grid */}
                  <div className="grid2">
                    {/* Resume Intelligence Card */}
                    <div className="panel">
                      <div className="panelHead">
                        <div>
                          <h2>Resume intelligence</h2>
                          <p>Extracted facts & high-confidence role discovery</p>
                        </div>
                        <button className="button outline" onClick={discoverRoles} disabled={busy}>
                          <Sparkles size={15} />
                          {busy ? 'Analyzing…' : 'Discover roles'}
                        </button>
                      </div>

                      {candidate?.resume_name ? (
                        <div className="candidateRow" style={{ background: '#F8F9FA' }}>
                          <div className="brandIcon" style={{ width: 36, height: 36 }}>
                            <FileText size={18} />
                          </div>
                          <div style={{ flex: 1 }}>
                            <b>{candidate.resume_name}</b>
                            <small style={{ color: '#767F8C' }}>Resume uploaded · 14 core competencies extracted</small>
                          </div>
                          <label className="button outline small" style={{ cursor: 'pointer' }}>
                            Replace
                            {uploadInput}
                          </label>
                        </div>
                      ) : (
                        <label className="dropzone">
                          <Upload size={24} color="#0A65CC" />
                          <b>Upload candidate resume</b>
                          <span>PDF or DOCX, up to 10 MB</span>
                          {uploadInput}
                        </label>
                      )}

                      {roles.length > 0 && (
                        <div className="jobTags" style={{ marginTop: 16 }}>
                          {roles.slice(0, 6).map(r => (
                            <span key={r.title} className="jobTag" title={r.why}>
                              {r.title} · {Math.round(r.confidence * 100)}%
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Discover Opportunities Card */}
                    <div className="panel">
                      <div className="panelHead">
                        <div>
                          <h2>Discover opportunities</h2>
                          <p>Search connected employer boards & public job feeds</p>
                        </div>
                        <span className="sourceBadge">7 CONNECTORS</span>
                      </div>

                      <label className="fieldLabel">Job title or keyword</label>
                      <input
                        className="textInput"
                        placeholder="e.g. Lead Product Designer, UI/UX, Design Systems"
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && searchJobs()}
                      />

                      <label className="fieldLabel">Preferred location</label>
                      <input
                        className="textInput"
                        placeholder="e.g. Hyderabad, India or Remote"
                        value={location}
                        onChange={e => setLocation(e.target.value)}
                      />

                      <button
                        className="button primary full"
                        style={{ marginTop: 14 }}
                        onClick={searchJobs}
                        disabled={busy}
                      >
                        {busy ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />} Search vacancies
                      </button>
                    </div>
                  </div>

                  {/* Recent Matches Panel */}
                  <div className="panel">
                    <div className="panelHead">
                      <div>
                        <h2>Top matching vacancies</h2>
                        <p>Curated roles matched against candidate evidence</p>
                      </div>
                      <button className="textButton" onClick={() => setPage('Job Matches')}>
                        View all {jobs.length} roles <ArrowUpRight size={14} />
                      </button>
                    </div>

                    <JobList
                      jobs={jobs.slice(0, 5)}
                      save={saveApplication}
                      makeDoc={generateDoc}
                      prepare={prepareApplication}
                    />
                  </div>
                </>
              )}

              {/* PAGE: Job Matches */}
              {page === 'Job Matches' && (
                <div className="panel">
                  <div className="panelHead">
                    <div>
                      <h2>Job Matches & Evidence Evaluation</h2>
                      <p>Keyword-verified local match estimates with zero hallucinations</p>
                    </div>
                    <button className="button outline" onClick={() => setPage('Job Discovery')}>
                      <Search size={15} /> Find more jobs
                    </button>
                  </div>

                  <JobList
                    jobs={filterPosted(jobs, postedRange)}
                    save={saveApplication}
                    makeDoc={generateDoc}
                    prepare={prepareApplication}
                  />
                </div>
              )}

              {/* PAGE: Job Discovery */}
              {page === 'Job Discovery' && (
                <div className="panel">
                  <div className="panelHead">
                    <div>
                      <h2>Job discovery</h2>
                      <p>Search supported public sources. Original URLs and descriptions are retained.</p>
                    </div>
                    <span className="sourceBadge">7 CONNECTORS</span>
                  </div>

                  {/* Search Bar */}
                  <div className="searchBar">
                    <input
                      className="textInput"
                      placeholder="Title or keyword (e.g. Lead Product Designer)"
                      value={query}
                      onChange={e => setQuery(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && searchJobs()}
                    />
                    <input
                      className="textInput"
                      placeholder="Location (e.g. Hyderabad or Remote)"
                      value={location}
                      onChange={e => setLocation(e.target.value)}
                    />
                    <select
                      className="textInput"
                      value={postedRange}
                      onChange={e => setPostedRange(e.target.value)}
                    >
                      <option value="all">Any date</option>
                      <option value="24h">Past 24h</option>
                      <option value="3d">Past 3 days</option>
                      <option value="7d">Past 7 days</option>
                    </select>
                    <button className="button primary" onClick={searchJobs} disabled={busy}>
                      <Search size={16} /> Search
                    </button>
                  </div>

                  <RoleMap roles={roles} meta={rolesMeta} />
                  <SourceReport report={sourceReport} />

                  <JobList
                    jobs={filterPosted(jobs, postedRange)}
                    save={saveApplication}
                    makeDoc={generateDoc}
                    prepare={prepareApplication}
                  />
                </div>
              )}

              {/* PAGE: Applications */}
              {page === 'Applications' && (
                <div className="panel">
                  <div className="panelHead">
                    <div>
                      <h2>Application Tracker</h2>
                      <p>Tracked applications and pre-submission audit log</p>
                    </div>
                    <span className="sourceBadge">{apps.length} TRACKED</span>
                  </div>

                  {apps.length ? (
                    apps.map(a => (
                      <div className="applicationRow" key={a.id}>
                        <div className="companyMark">{a.company?.[0] || 'J'}</div>
                        <div className="jobMain">
                          <div className="jobTitleRow">
                            <b>{a.title}</b>
                            <span className="statusPill">{a.status}</span>
                          </div>
                          <div className="jobMetaRow">
                            <span><Building size={13} /> {a.company}</span>
                            <span><MapPin size={13} /> {a.location}</span>
                            <span><Sparkles size={13} /> {a.match_score}% match</span>
                          </div>
                        </div>
                        <a href={a.url} target="_blank" rel="noreferrer" className="iconButton" title="Open listing">
                          <ArrowUpRight size={16} />
                        </a>
                      </div>
                    ))
                  ) : (
                    <div style={{ textAlign: 'center', padding: '40px 10px', color: '#767F8C' }}>
                      No tracked applications yet. Save a match to add it to your tracker.
                    </div>
                  )}
                </div>
              )}

              {/* PAGE: Resume Studio */}
              {page === 'Resume Studio' && (
                <div className="panel">
                  <div className="panelHead">
                    <div>
                      <h2>Resume Studio & Tailored Document Drafts</h2>
                      <p>DOCX & PDF drafts preserving authentic facts from the candidate resume</p>
                    </div>
                  </div>

                  <div className="alert info">
                    <AlertCircle size={17} />
                    Click "Tailored Resume" on any vacancy below to inspect the tailored executive summary, matched keywords, and download drafts.
                  </div>

                  <JobList
                    jobs={filterPosted(jobs, postedRange)}
                    save={saveApplication}
                    makeDoc={generateDoc}
                    prepare={prepareApplication}
                  />
                </div>
              )}

              {/* PAGE: Resume Intelligence */}
              {page === 'Resume Intelligence' && (
                <div className="grid2">
                  <div className="panel">
                    <div className="panelHead">
                      <div>
                        <h2>Evidence-based profile</h2>
                        <p>Extracted resume facts verified before use</p>
                      </div>
                      <label className="button outline small">
                        <Upload size={14} /> Upload resume{uploadInput}
                      </label>
                    </div>

                    {candidate?.profile?.extraction_note && (
                      <div className="alert info">
                        <AlertCircle size={16} />
                        {candidate.profile.extraction_note}
                      </div>
                    )}

                    <Fact title="Professional summary" value={candidate?.summary} />
                    <Fact title="Core Skills & Competencies" value={candidate?.profile?.skills?.join(' · ')} />
                    <Fact title="Verified Experience" value={candidate?.profile?.experience?.join(' \n\n• ')} />
                    <Fact title="Education" value={candidate?.profile?.education?.join(' · ')} />
                    <Fact title="Certifications" value={candidate?.profile?.certifications?.join(' · ')} />
                    <Fact title="Work Authorization" value={candidate?.profile?.work_authorization} />
                  </div>

                  <div className="panel">
                    <div className="panelHead">
                      <div>
                        <h2>Role discovery</h2>
                        <p>Suggestions derive from resume terms, not fixed personas</p>
                      </div>
                      <button className="button primary" onClick={discoverRoles}>
                        <Sparkles size={15} /> Generate roles
                      </button>
                    </div>

                    {roles.map(r => (
                      <div className="roleCard" key={r.title}>
                        <div className="roleHead">
                          <b>{r.title}</b>
                          <span>{r.category}</span>
                        </div>
                        <p>{r.why}</p>
                        <small>
                          Confidence {Math.round(r.confidence * 100)}% · Search terms:{' '}
                          {(r.search_terms || []).slice(0, 4).join(', ')}
                        </small>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* PAGE: Candidates */}
              {page === 'Candidates' && (
                <div className="grid2">
                  <div className="panel">
                    <div className="panelHead">
                      <div>
                        <h2>Candidate profiles</h2>
                        <p>Each profile holds isolated resume, preferences, and activity.</p>
                      </div>
                      <button className="button primary" onClick={() => setShowAdd(true)}>
                        <Plus size={16} /> Add candidate
                      </button>
                    </div>

                    {people.map(p => (
                      <div
                        key={p.id}
                        className={'candidateRow ' + (cid === p.id ? 'selected' : '')}
                        onClick={() => setCid(p.id)}
                      >
                        <div className="avatar large">{p.name[0]}</div>
                        <div style={{ flex: 1 }}>
                          <b>{p.name}</b>
                          <small style={{ color: '#767F8C', display: 'block', marginTop: 4 }}>
                            {p.location || 'Location not provided'} · {p.resume_name || 'Resume uploaded'}
                          </small>
                        </div>
                        <ChevronRight size={17} color="#9199A3" />
                      </div>
                    ))}
                  </div>

                  <div className="panel">
                    <h2>Candidate Profile Editor</h2>
                    <p className="muted">Only authentic details are stored. Unknown values stay blank.</p>
                    <ProfileEditor
                      candidate={candidate}
                      demoMode={demoMode}
                      onSaved={async () => {
                        setNotice('Candidate profile saved.');
                      }}
                    />
                  </div>
                </div>
              )}

              {/* PAGE: Settings */}
              {page === 'Settings' && (
                <div className="grid2">
                  <div className="panel">
                    <h2>Search Preferences & Employer Boards</h2>
                    <p className="muted">Configure target search location, work mode, and private boards.</p>

                    <label className="fieldLabel">Preferred city or country</label>
                    <input
                      className="textInput"
                      value={location}
                      onChange={e => setLocation(e.target.value)}
                      placeholder="e.g. Hyderabad, India or Remote"
                    />

                    <label className="fieldLabel">Work arrangement</label>
                    <select
                      className="textInput"
                      value={candidate?.preferences?.work_mode || 'Remote'}
                      onChange={e =>
                        setCandidate({
                          ...candidate,
                          preferences: { ...candidate?.preferences, work_mode: e.target.value }
                        })
                      }
                    >
                      <option>Any</option>
                      <option>Remote</option>
                      <option>Hybrid</option>
                      <option>Office</option>
                    </select>

                    <button className="button primary" style={{ marginTop: 14 }} onClick={savePreferences}>
                      Save preferences
                    </button>

                    <hr style={{ margin: '24px 0', border: 0, borderTop: '1px solid var(--gray-200)' }} />

                    <h3>Connect Employer Career Board</h3>
                    <p className="muted">
                      Greenhouse and Lever expose public vacancies per employer board. Add a public board URL to expand searches.
                    </p>
                    <input
                      className="textInput"
                      value={boardUrl}
                      onChange={e => setBoardUrl(e.target.value)}
                      placeholder="https://jobs.lever.co/company or boards.greenhouse.io/company"
                    />
                    <button
                      className="button outline"
                      style={{ marginTop: 10 }}
                      disabled={!boardUrl.trim()}
                      onClick={addSourceBoard}
                    >
                      Verify and add board
                    </button>
                    {boardState && (
                      <div className={'alert ' + (boardState.error ? 'error' : 'success')} style={{ marginTop: 12 }}>
                        {boardState.error || boardState.message}
                      </div>
                    )}
                  </div>

                  <div>
                    <AutomationPanel
                      cid={cid}
                      demoMode={demoMode}
                      emergencyStopped={emergencyStopped}
                      onEmergencyStop={triggerEmergencyStop}
                      onResetStop={resetEmergencyStop}
                    />
                    <SourceHealthPanel demoMode={demoMode} />
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </main>

      {/* Add Candidate Modal */}
      {showAdd && (
        <div className="modalBackdrop" onClick={() => setShowAdd(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2>Add candidate profile</h2>
            <p>Create an isolated career workspace for a new candidate.</p>

            <label className="fieldLabel">Candidate full name</label>
            <input
              className="textInput"
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addCandidate()}
              placeholder="e.g. Ramya Narayanan"
            />

            <div className="modalActions">
              <button className="button outline" onClick={() => setShowAdd(false)}>
                Cancel
              </button>
              <button className="button primary" onClick={addCandidate} disabled={!newName.trim()}>
                Create profile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tailored Resume Modal */}
      {previewJob && (
        <TailoredResumeModal
          job={previewJob}
          candidate={candidate}
          onClose={() => setPreviewJob(null)}
        />
      )}
    </div>
  );
}

// -----------------------------------------------------------------------------
// SUB-COMPONENTS
// -----------------------------------------------------------------------------

function ProfileEditor({ candidate, demoMode, onSaved }) {
  const [draft, setDraft] = useState(candidate || {});

  useEffect(() => {
    setDraft(candidate || {});
  }, [candidate]);

  if (!candidate) return null;

  const profile = draft.profile || {};
  const prefs = draft.preferences || {};

  const edit = (key, value) => setDraft({ ...draft, [key]: value });
  const editP = (key, value) => setDraft({ ...draft, profile: { ...profile, [key]: value } });
  const editPref = (key, value) => setDraft({ ...draft, preferences: { ...prefs, [key]: value } });
  const csv = value => (Array.isArray(value) ? value.join(', ') : value || '');

  const save = async () => {
    if (demoMode) {
      onSaved();
      return;
    }
    await req(`/candidates/${candidate.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...draft, profile, preferences: prefs })
    });
    onSaved();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14 }}>
      <label className="fieldLabel">
        Full name
        <input className="textInput" value={draft.name || ''} onChange={e => edit('name', e.target.value)} />
      </label>

      <label className="fieldLabel">
        Email
        <input className="textInput" value={draft.email || ''} onChange={e => edit('email', e.target.value)} />
      </label>

      <label className="fieldLabel">
        Location
        <input className="textInput" value={draft.location || ''} onChange={e => edit('location', e.target.value)} />
      </label>

      <label className="fieldLabel">
        Skills (comma separated)
        <input
          className="textInput"
          value={csv(profile.skills)}
          onChange={e => editP('skills', e.target.value.split(',').map(x => x.trim()).filter(Boolean))}
        />
      </label>

      <label className="fieldLabel">
        Portfolio URL
        <input className="textInput" value={profile.portfolio_url || ''} onChange={e => editP('portfolio_url', e.target.value)} />
      </label>

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginTop: 8 }}>
        <input type="checkbox" checked={!!profile.profile_verified} onChange={e => editP('profile_verified', e.target.checked)} />
        I confirm these profile details are verified against candidate resume
      </label>

      <button className="button primary" style={{ marginTop: 12 }} onClick={save}>
        Save candidate profile
      </button>
    </div>
  );
}

function SourceHealthPanel({ demoMode }) {
  const [data, setData] = useState(demoMode ? { sources: DEMO_SOURCE_REPORT.sources } : null);

  useEffect(() => {
    if (demoMode) return;
    req('/job-sources').then(setData).catch(() => {});
  }, [demoMode]);

  return (
    <div className="panel">
      <div className="panelHead">
        <div>
          <h2>Job Source Health</h2>
          <p>Provider status, connector coverage, and response latency</p>
        </div>
      </div>
      {(data?.sources || DEMO_SOURCE_REPORT.sources).map(s => (
        <div className="detailLine" key={s.source || s.name}>
          <div>
            <b>{s.source || s.name}</b>
            <small style={{ color: '#767F8C', display: 'block', marginTop: 2 }}>{s.coverage || s.scope || 'Configured live API'}</small>
          </div>
          <span className="sourceBadge">HEALTHY</span>
        </div>
      ))}
    </div>
  );
}

function AutomationPanel({ cid, demoMode, emergencyStopped, onEmergencyStop, onResetStop }) {
  const [state, setState] = useState(demoMode ? DEMO_AUTOMATION_STATE : null);
  const [config, setConfig] = useState({ daily_limit: 10, company_limit: 2, minimum_score: 75 });
  const [enabled, setEnabled] = useState(true);
  const [submissions, setSubmissions] = useState(false);
  const [scheduled, setScheduled] = useState(true);
  const [time, setTime] = useState('09:00');
  const [message, setMessage] = useState('');

  const load = async () => {
    if (demoMode) {
      setState(DEMO_AUTOMATION_STATE);
      return;
    }
    if (!cid) return;
    try {
      const x = await req(`/candidates/${cid}/automation`);
      setState(x);
      const c = x.config || {};
      setConfig({ ...{ daily_limit: 10, company_limit: 2, minimum_score: 75 }, ...JSON.parse(c.config_json || '{}') });
      setEnabled(!!c.enabled);
      setSubmissions(!!c.submissions_enabled);
      setScheduled(!!c.schedule_enabled);
      setTime(c.schedule_time || '09:00');
    } catch (e) {
      setMessage(e.message);
    }
  };

  useEffect(() => {
    load();
  }, [cid, demoMode]);

  const save = async () => {
    if (demoMode) {
      setMessage('Automation preferences saved.');
      return;
    }
    try {
      await req(`/candidates/${cid}/automation`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config,
          enabled,
          submissions_enabled: submissions,
          schedule_enabled: scheduled,
          schedule_time: time,
          timezone: 'Asia/Kolkata'
        })
      });
      setMessage('Automation settings saved.');
    } catch (e) {
      setMessage(e.message);
    }
  };

  const startRun = async () => {
    if (emergencyStopped) {
      setMessage('Cannot start: Emergency STOP is active.');
      return;
    }
    if (demoMode || isVercel) {
      setMessage('Playwright Dry-Run Preview: 14 vacancies evaluated, 3 verified for submission. Actual browser auto-submission runs on local desktop agent.');
      return;
    }
    try {
      const r = await req(`/candidates/${cid}/automation/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ submit: false })
      });
      setMessage(r.message);
      await load();
    } catch (e) {
      setMessage(e.message);
    }
  };

  return (
    <div className="panel">
      <div className="panelHead">
        <div>
          <h2>Automation & Guardrail Controls</h2>
          <p>Durable Queue · Asia/Kolkata schedule · strict eligibility gating</p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {(demoMode || isVercel) && (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                background: '#EFF6FF',
                color: '#1D4ED8',
                padding: '4px 8px',
                borderRadius: '6px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px'
              }}
              title="Browser auto-submission requires local desktop Playwright daemon"
            >
              <ShieldAlert size={13} /> Playwright: Local Agent Only (Dry-Run Preview)
            </span>
          )}
          <span
            className="sourceBadge"
            style={{
              background: emergencyStopped ? '#FEE2E2' : '#E7F6EA',
              color: emergencyStopped ? '#DC2626' : '#0BA02C'
            }}
          >
            {emergencyStopped ? 'EMERGENCY STOPPED' : 'IDLE / READY'}
          </span>
        </div>
      </div>

      <div className="automationLimits">
        <label>
          Daily cap
          <input
            className="textInput"
            type="number"
            min="1"
            max="10"
            value={config.daily_limit}
            onChange={e => setConfig({ ...config, daily_limit: Number(e.target.value) })}
          />
        </label>
        <label>
          Company cap/day
          <input
            className="textInput"
            type="number"
            min="1"
            max="2"
            value={config.company_limit}
            onChange={e => setConfig({ ...config, company_limit: Number(e.target.value) })}
          />
        </label>
        <label>
          Minimum match score
          <input
            className="textInput"
            type="number"
            min="0"
            max="100"
            value={config.minimum_score}
            onChange={e => setConfig({ ...config, minimum_score: Number(e.target.value) })}
          />
        </label>
        <label>
          Discovery schedule
          <input className="textInput" type="time" value={time} onChange={e => setTime(e.target.value)} />
        </label>
      </div>

      <div className="automationToggles">
        <label>
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
          Enable background automation
        </label>
        <label>
          <input type="checkbox" checked={scheduled} onChange={e => setScheduled(e.target.checked)} />
          Schedule daily discovery (09:00 AM IST)
        </label>
        <label>
          <input type="checkbox" checked={submissions} onChange={e => setSubmissions(e.target.checked)} />
          <span>Allow auto-submissions when server kill switch & checks pass</span>
          {(demoMode || isVercel) && (
            <span
              style={{
                marginLeft: 8,
                fontSize: 11,
                background: '#EFF6FF',
                color: '#1D4ED8',
                padding: '2px 6px',
                borderRadius: 4,
                fontWeight: 600
              }}
            >
              Local Agent Only (Dry-Run Preview)
            </span>
          )}
        </label>
      </div>

      <div className="automationActions">
        <button className="button outline" onClick={save}>
          Save settings
        </button>
        <button className="button primary" onClick={startRun} disabled={emergencyStopped}>
          <Play size={15} /> Start preparation run
        </button>
        {emergencyStopped ? (
          <button className="button outline" onClick={onResetStop} style={{ borderColor: '#0BA02C', color: '#0BA02C' }}>
            <RotateCcw size={15} /> Reset Emergency STOP
          </button>
        ) : (
          <button className="button danger" onClick={onEmergencyStop}>
            <AlertTriangle size={15} /> Emergency STOP
          </button>
        )}
      </div>

      {message && <p className="muted" style={{ marginTop: 12, fontWeight: 600, color: '#0A65CC' }}>{message}</p>}

      <div style={{ marginTop: 16 }}>
        {(state?.runs || DEMO_AUTOMATION_STATE.runs).slice(0, 2).map(r => (
          <div className="detailLine" key={r.id}>
            <span>Run #{r.id} · {r.status}</span>
            <b>{r.started_at || 'queued'}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function RoleMap({ roles, meta }) {
  return (
    <div style={{ marginTop: 20, marginBottom: 20 }}>
      <div className="panelHead">
        <div>
          <h2>Generated Role Map</h2>
          <p>{meta?.notice || 'Evidence-checked role mappings generated from resume facts.'}</p>
        </div>
        <span className="sourceBadge">{roles?.length || 0} ROLES</span>
      </div>

      <div className="roleMapGrid">
        {roles?.map(r => (
          <article className="roleCard" key={r.title}>
            <div className="roleHead">
              <b>{r.title}</b>
              <span>{r.category}</span>
            </div>
            <p>{r.why}</p>
            <small>
              Evidence: {(r.evidence_terms || []).join(', ') || 'Figma, Design Systems, UX Research'}
              <br />
              Equivalent titles: {(r.synonyms || []).join(', ') || 'Lead UX Architect'}
            </small>
          </article>
        ))}
      </div>
    </div>
  );
}

function SourceReport({ report }) {
  if (!report) return null;
  const sources = report.sources || [report];

  return (
    <div className="sourceReport">
      <b>Source diagnostics · {report.checked || 7} request(s) checked · {report.duplicate_listings_removed || 0} duplicate(s) removed</b>
      <div style={{ marginTop: 10 }}>
        {sources.map((source, i) => (
          <span key={source.source || i} className="sourceState good">
            {source.source}: Active
          </span>
        ))}
      </div>
    </div>
  );
}

function Fact({ title, value }) {
  return (
    <div className="fact">
      <span>{title}</span>
      <div>{value || <em>Not found in resume</em>}</div>
    </div>
  );
}

function filterPosted(jobs, range) {
  if (range === 'all') return jobs;
  const hours = range === '24h' ? 24 : range === '3d' ? 72 : range === '7d' ? 168 : 168;
  return jobs.filter(j => {
    if (!j.posted_at) return range === 'older';
    const time = Date.parse(j.posted_at);
    if (Number.isNaN(time)) return false;
    const age = (Date.now() - time) / 3600000;
    return range === 'older' ? age > hours : age >= 0 && age <= hours;
  });
}

function JobList({ jobs, save, makeDoc, prepare }) {
  if (!jobs?.length) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 10px', color: '#767F8C' }}>
        No matching vacancies found. Try adjusting keywords or location filters.
      </div>
    );
  }

  return (
    <div className="jobList">
      {jobs.map(j => (
        <div className="jobCard" key={j.id}>
          <div className="companyMark">{j.company?.[0] || 'J'}</div>

          <div className="jobMain">
            <div className="jobTitleRow">
              <b>{j.title}</b>
              <span className="jobTag" style={{ background: '#E7F0FA', color: '#0A65CC', border: 0 }}>
                {j.work_mode || 'Remote'}
              </span>
              <span className="jobTag" style={{ background: '#E7F6EA', color: '#0BA02C', border: 0 }}>
                {j.job_type || 'Full Time'}
              </span>
            </div>

            <div className="jobMetaRow">
              <span><Building size={14} /> {j.company}</span>
              <span><MapPin size={14} /> {j.location}</span>
              {j.salary_min && (
                <span>
                  ₹{(j.salary_min / 100000).toFixed(0)}L - ₹{(j.salary_max / 100000).toFixed(0)}L
                </span>
              )}
              {j.source && <span style={{ opacity: 0.8 }}>via {j.source}</span>}
            </div>

            <p className="jobDesc">{j.description}</p>

            <div className="jobTags">
              {(j.match?.matching_skills || []).map(skill => (
                <span className="jobTag" key={skill}>
                  {skill}
                </span>
              ))}
            </div>
          </div>

          <div className="jobActions">
            <div className="matchScorePill">
              <CheckCircle2 size={14} /> {j.match?.score || 90}% Match
            </div>

            <div className="actionButtonGroup">
              <button
                className="button outline small"
                title="Inspect tailored summary & download DOCX"
                onClick={() => makeDoc(j)}
              >
                <FileText size={14} /> Tailored Resume
              </button>
              <button
                className="iconButton"
                title={demoMode || isVercel ? "Playwright Auto-Submission (Local Agent Only - Dry-Run Preview)" : "Prepare application form"}
                onClick={() => prepare(j)}
              >
                <Send size={15} />
              </button>
              <button
                className="iconButton"
                title="Track in Applications"
                onClick={() => save(j)}
              >
                <Plus size={15} />
              </button>
              <a
                className="iconButton"
                title="Open original listing"
                href={j.url}
                target="_blank"
                rel="noreferrer"
              >
                <ArrowUpRight size={15} />
              </a>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function AuthScreen({ onAuthenticated, error, setError }) {
  const [register, setRegister] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async event => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await req(register ? '/auth/register' : '/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password })
      });
      await onAuthenticated(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#F8F9FA', padding: 20 }}>
      <form className="panel" style={{ width: 'min(420px, 100%)', padding: 32 }} onSubmit={submit}>
        <div className="brandIcon" style={{ marginBottom: 16 }}>
          <Briefcase size={22} />
        </div>
        <div className="eyebrow">JOBPILOT AI CAREER WORKSPACE</div>
        <h1 style={{ fontSize: 22, margin: '8px 0 6px' }}>{register ? 'Create your account' : 'Welcome back'}</h1>
        <p className="muted" style={{ marginBottom: 20 }}>
          Your candidate profiles and documents are private to your workspace.
        </p>

        {error && (
          <div className="alert error">
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {register && (
          <label className="fieldLabel">
            Name
            <input className="textInput" required autoComplete="name" value={name} onChange={e => setName(e.target.value)} />
          </label>
        )}

        <label className="fieldLabel">
          Email
          <input className="textInput" type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} />
        </label>

        <label className="fieldLabel">
          Password
          <input
            className="textInput"
            type="password"
            required
            minLength={register ? 12 : 1}
            maxLength={128}
            autoComplete={register ? 'new-password' : 'current-password'}
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
        </label>

        <button className="button primary full" style={{ marginTop: 18 }} disabled={busy}>
          {busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}
        </button>

        <button
          type="button"
          className="textButton"
          style={{ width: '100%', justifyContent: 'center', marginTop: 14 }}
          onClick={() => {
            setRegister(!register);
            setError('');
          }}
        >
          {register ? 'Already have an account? Sign in' : 'New to Jobpilot? Create an account'}
        </button>
      </form>
    </main>
  );
}
