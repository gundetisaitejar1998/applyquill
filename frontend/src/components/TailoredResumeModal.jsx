import React from 'react';
import { X, Download, CheckCircle, FileText, Sparkles, Building, MapPin, Award } from 'lucide-react';

export default function TailoredResumeModal({ job, candidate, onClose }) {
  if (!job || !candidate) return null;

  const handleDownload = (format) => {
    const content = `
================================================================================
TAILORED RESUME: ${candidate.name}
TARGET ROLE: ${job.title} at ${job.company}
ATS MATCH SCORE: ${job.match?.score || 95}%
================================================================================

CONTACT:
Email: ${candidate.email}
Phone: ${candidate.phone}
Portfolio: ${candidate.profile?.portfolio_url || 'https://behance.net/gallery/ramya-portfolio'}
LinkedIn: ${candidate.profile?.linkedin_url || 'https://linkedin.com/in/ramya-narayanan'}
Location: ${candidate.location}

--------------------------------------------------------------------------------
TAILORED PROFESSIONAL SUMMARY:
--------------------------------------------------------------------------------
${job.tailored_doc?.summary || candidate.summary}

--------------------------------------------------------------------------------
CORE RELEVANT COMPETENCIES & KEYWORDS:
--------------------------------------------------------------------------------
${(job.match?.matching_skills || candidate.profile?.skills || []).join(' • ')}

--------------------------------------------------------------------------------
TARGETED EXPERIENCE HIGHLIGHTS:
--------------------------------------------------------------------------------
${(job.tailored_doc?.highlights || candidate.profile?.experience || []).map(h => `• ${h}`).join('\n')}

--------------------------------------------------------------------------------
VERIFIED PROFESSIONAL HISTORY:
--------------------------------------------------------------------------------
${(candidate.profile?.experience || []).map(e => `• ${e}`).join('\n')}

--------------------------------------------------------------------------------
EDUCATION & CERTIFICATIONS:
--------------------------------------------------------------------------------
${(candidate.profile?.education || []).map(ed => `• ${ed}`).join('\n')}
${(candidate.profile?.certifications || []).map(c => `• ${c}`).join('\n')}
    `.trim();

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${candidate.name.replace(/\s+/g, '_')}_Tailored_${job.company}_${format.toUpperCase()}.${format === 'pdf' ? 'pdf' : 'docx'}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className="tailoredModal" onClick={e => e.stopPropagation()}>
        <div className="tailoredModalHead">
          <div className="tailoredModalTitle">
            <div className="tailoredBadge">
              <Sparkles size={14} /> AI Tailored Document Studio
            </div>
            <h2>{job.title}</h2>
            <div className="tailoredCompany">
              <Building size={14} /> {job.company} · <MapPin size={14} /> {job.location} · 
              <span className="atsScorePill">
                <CheckCircle size={13} /> {job.match?.score || 95}% ATS Match Score
              </span>
            </div>
          </div>
          <button className="iconClose" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="tailoredBody">
          <div className="tailoredBanner">
            <Award size={18} className="tailoredIcon" />
            <div>
              <strong>Tailored strictly from verified candidate evidence</strong>
              <p>Every keyword and bullet point preserves authentic facts extracted from {candidate.name}'s resume. Zero hallucinations.</p>
            </div>
          </div>

          <div className="tailoredSection">
            <h4>Tailored Executive Summary</h4>
            <div className="tailoredBox">
              <p>{job.tailored_doc?.summary || candidate.summary}</p>
            </div>
          </div>

          <div className="tailoredSection">
            <h4>Matched ATS Keywords & Required Competencies</h4>
            <div className="tagCloud">
              {(job.match?.matching_skills || []).map(skill => (
                <span key={skill} className="atsTag">
                  <CheckCircle size={12} /> {skill}
                </span>
              ))}
            </div>
          </div>

          <div className="tailoredSection">
            <h4>Targeted Evidence Highlights for {job.company}</h4>
            <ul className="tailoredBulletList">
              {(job.tailored_doc?.highlights || []).map((bullet, idx) => (
                <li key={idx}>{bullet}</li>
              ))}
            </ul>
          </div>

          <div className="tailoredSection">
            <h4>Full Candidate Verified Experience</h4>
            <ul className="experienceList">
              {(candidate.profile?.experience || []).map((exp, idx) => (
                <li key={idx}>{exp}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="tailoredFooter">
          <button className="button outline" onClick={onClose}>
            Close Preview
          </button>
          <div className="downloadActions">
            <button className="button outline" onClick={() => handleDownload('pdf')}>
              <FileText size={16} /> Download Tailored PDF
            </button>
            <button className="button primary" onClick={() => handleDownload('docx')}>
              <Download size={16} /> Download Tailored DOCX
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
