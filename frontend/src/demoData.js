// Sample realistic data for Ramya Narayanan (Senior Product & UI/UX Designer)
// Used when VITE_DEMO_MODE=true or when deployed on Vercel Hobby for Behance Portfolio

export const DEMO_CANDIDATES = [
  {
    id: 1,
    name: "Ramya Narayanan",
    location: "Hyderabad, India (Open to Remote / Relocation)",
    email: "ramya.design@example.com",
    phone: "+91 98765 43210",
    resume_name: "Ramya_Narayanan_Lead_Product_Designer.pdf",
    resume_path: "/uploads/resumes/Ramya_Narayanan_Lead_Product_Designer.pdf",
    summary:
      "Senior Product & UI/UX Designer with 6+ years of experience leading cross-functional teams, architecting enterprise design systems, conducting qualitative user research, and crafting high-conversion B2B/B2C SaaS experiences in Figma, React, and Design Tokens.",
    profile: {
      location: "Hyderabad, India",
      portfolio_url: "https://behance.net/gallery/ramya-product-designer",
      linkedin_url: "https://linkedin.com/in/ramya-narayanan-design",
      work_authorization: "India Citizen (OCI / Authorized for Global Remote)",
      profile_verified: true,
      skills: [
        "Figma",
        "Design Systems",
        "UI/UX Architecture",
        "User Research & Usability Testing",
        "Wireframing & Prototyping",
        "Information Architecture",
        "Design Tokens",
        "Interaction Design",
        "Framer",
        "React & Tailwind CSS",
        "Micro-interactions",
        "Accessibility (WCAG AA)",
        "Design Thinking",
        "Cross-Functional Collaboration"
      ],
      experience: [
        "Lead Product Designer · FinTech Innovators (2022 - Present) · Architected zero-to-one design system used across 14 product squads; improved designer-developer handoff velocity by 40%.",
        "Senior UI/UX Designer · CloudScale SaaS (2020 - 2022) · Led end-to-end redesign of analytics dashboard, driving a 28% increase in 30-day user retention.",
        "Product Designer · StudioCraft Digital (2018 - 2020) · Created user journeys, wireframes, and prototypes for global e-commerce and mobility apps."
      ],
      education: [
        "B.Des in Interaction Design · National Institute of Design (NID)",
        "Human-Computer Interaction Certification · Nielsen Norman Group (NN/g)"
      ],
      certifications: [
        "NN/g UX Master Certified (2023)",
        "Enterprise Design Thinking Co-Creator · IBM (2022)"
      ],
      languages: ["English (Fluent)", "Hindi (Fluent)", "Telugu (Native)"],
      extraction_note: "Resume verified: 14 core design competencies and 6+ years SaaS design leadership extracted."
    },
    preferences: {
      preferred_roles: [
        "Lead Product Designer",
        "Senior UI/UX Designer",
        "Design System Lead",
        "Staff Product Designer"
      ],
      cities: ["Hyderabad, India", "Bengaluru, India", "Remote (Global)"],
      work_mode: "Remote",
      employment_types: ["Full-time", "Contract"],
      experience_levels: ["Senior", "Lead", "Staff"],
      remote_countries: ["India", "United States", "United Kingdom", "Singapore"],
      salary_min: 3600000,
      salary_currency: "INR"
    }
  },
  {
    id: 2,
    name: "Alex Chen",
    location: "Bengaluru, India",
    email: "alex.chen.ux@example.com",
    phone: "+91 91234 56789",
    resume_name: "Alex_Chen_Principal_Interaction_Designer.pdf",
    resume_path: "/uploads/resumes/Alex_Chen_Principal_Interaction_Designer.pdf",
    summary:
      "Principal Interaction Designer specializing in spatial design, generative AI interface paradigms, and design system governance.",
    profile: {
      location: "Bengaluru, India",
      portfolio_url: "https://behance.net/gallery/alex-chen-interactions",
      linkedin_url: "https://linkedin.com/in/alex-chen-interactions",
      work_authorization: "India Citizen",
      profile_verified: true,
      skills: ["Interaction Design", "Figma", "Micro-interactions", "Design Systems", "Prototyping", "Design Tokens"],
      experience: ["Principal Interaction Designer · Apex Labs (2021 - Present)", "Senior UX Designer · DataViz Inc (2018 - 2021)"],
      education: ["M.Des Interaction Design · IIT Bombay"],
      certifications: ["IDF Interaction Design Specialist"],
      languages: ["English", "Hindi"]
    },
    preferences: {
      preferred_roles: ["Principal Interaction Designer", "Staff UX Designer"],
      cities: ["Bengaluru, India", "Remote"],
      work_mode: "Remote",
      salary_min: 4000000,
      salary_currency: "INR"
    }
  }
];

export const DEMO_ROLES = [
  {
    title: "Lead Product Designer",
    category: "Product Design",
    confidence: 0.98,
    why: "Direct match to 6+ years leading SaaS product suites, enterprise design systems, and cross-functional teams.",
    search_terms: ["Lead Product Designer", "Principal Product Designer", "Head of Product Design"],
    evidence_terms: ["Design Systems", "Product Strategy", "Figma", "SaaS", "40% velocity improvement"],
    synonyms: ["Lead UX Designer", "Product Design Lead", "Principal UI Designer"]
  },
  {
    title: "Senior UI/UX Designer",
    category: "User Experience",
    confidence: 0.95,
    why: "Strong portfolio in end-to-end user research, interaction design, information architecture, and design tokens.",
    search_terms: ["Senior UI/UX Designer", "Senior Product Designer", "UI/UX Specialist"],
    evidence_terms: ["User Research", "Wireframing", "Prototyping", "Usability Testing", "Design Tokens"],
    synonyms: ["Senior UX/UI Specialist", "Senior UX Designer"]
  },
  {
    title: "Design System Lead",
    category: "Design Systems",
    confidence: 0.92,
    why: "Proven track record building multi-squad component libraries and managing design tokens between Figma and React.",
    search_terms: ["Design System Lead", "Design Technologist", "Design Infrastructure Lead"],
    evidence_terms: ["Design System Governance", "Figma Components", "Design Tokens", "React handoff"],
    synonyms: ["Design Systems Architect", "Component Library Specialist"]
  },
  {
    title: "Principal Interaction Designer",
    category: "Interaction Design",
    confidence: 0.88,
    why: "High proficiency in micro-interactions, complex workflow simplification, and accessibility standards (WCAG AA).",
    search_terms: ["Interaction Designer", "Principal Interaction Designer", "UX Architect"],
    evidence_terms: ["Micro-interactions", "Framer", "Prototyping", "WCAG AA", "Complex Workflows"],
    synonyms: ["Senior Interaction Designer", "Lead UX Architect"]
  }
];

export const DEMO_JOBS = [
  {
    id: 101,
    title: "Senior Product Designer - Design Systems",
    company: "Stripe",
    location: "Remote (Global / APAC)",
    work_mode: "Remote",
    job_type: "Full Time",
    salary_min: 3800000,
    salary_max: 5200000,
    salary_currency: "INR",
    posted_at: new Date(Date.now() - 4 * 3600000).toISOString(),
    discovered_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    source: "Greenhouse",
    url: "https://stripe.com/jobs",
    description:
      "Stripe is seeking an experienced Senior Product Designer to join our Core Design Systems team. In this role, you will evolve foundational Figma libraries, design tokens, and web/mobile component architecture used by hundreds of engineers and designers worldwide. You will partner with engineers to ensure WCAG AA accessibility, create interactive documentation, and champion design craft across all merchant touchpoints.",
    match: {
      score: 98,
      matching_skills: ["Figma", "Design Systems", "Design Tokens", "Accessibility (WCAG AA)", "Cross-Functional Collaboration"],
      explanation: "Exceptional alignment: Candidate led zero-to-one design system across 14 squads and established token workflows.",
      eligibility_note: "Candidate exceeds experience and token governance requirements. No sponsorship blockers."
    },
    eligibility: {
      status: "Eligible",
      reasons: ["98% skill overlap", "Meets 6+ years seniority requirement", "Remote India/APAC timezone compatible"]
    },
    tailored_doc: {
      summary: "Senior Product Designer with 6+ years experience architecting multi-squad design systems and Figma design tokens.",
      highlights: [
        "Engineered zero-to-one multi-platform design system at FinTech Innovators with WCAG AA compliance.",
        "Cut designer-developer handoff friction by 40% using automated Figma-to-token sync.",
        "Partnered with frontend engineers to standardize accessible React components."
      ]
    }
  },
  {
    id: 102,
    title: "Lead UI/UX Designer - B2B SaaS",
    company: "Figma",
    location: "Hyderabad, India / Remote",
    work_mode: "Hybrid",
    job_type: "Full Time",
    salary_min: 4200000,
    salary_max: 5800000,
    salary_currency: "INR",
    posted_at: new Date(Date.now() - 14 * 3600000).toISOString(),
    discovered_at: new Date(Date.now() - 8 * 3600000).toISOString(),
    source: "Lever",
    url: "https://figma.com/careers",
    description:
      "Figma is looking for a Lead UI/UX Designer to drive zero-to-one product initiatives for collaborative enterprise workflows. You will lead generative user research, architect complex multi-modal interfaces, prototype fluid interactions, and shape the future of visual collaboration for millions of creators.",
    match: {
      score: 96,
      matching_skills: ["UI/UX Architecture", "Wireframing & Prototyping", "User Research & Usability Testing", "Interaction Design", "Figma"],
      explanation: "Direct role match: 6+ years SaaS product design, proven research methodologies, and collaborative workflow mastery.",
      eligibility_note: "Full match for Hyderabad/Remote hub. Meets leadership criteria."
    },
    eligibility: {
      status: "Eligible",
      reasons: ["96% skill overlap", "Proven leadership in B2B SaaS", "Matches preferred work location"]
    },
    tailored_doc: {
      summary: "Lead UI/UX Designer passionate about collaborative software, usability testing, and fluid prototyping.",
      highlights: [
        "Led end-to-end user research across 35+ enterprise client accounts to uncover key workflow pain points.",
        "Redesigned analytics dashboard for CloudScale SaaS, increasing 30-day user retention by 28%.",
        "Expert in rapid Figma prototyping and interactive micro-interactions."
      ]
    }
  },
  {
    id: 103,
    title: "Staff Product Designer - Core Experience",
    company: "Notion",
    location: "Remote (India / Global)",
    work_mode: "Remote",
    job_type: "Full Time",
    salary_min: 4000000,
    salary_max: 5500000,
    salary_currency: "INR",
    posted_at: new Date(Date.now() - 22 * 3600000).toISOString(),
    discovered_at: new Date(Date.now() - 10 * 3600000).toISOString(),
    source: "Remotive",
    url: "https://notion.so/careers",
    description:
      "As a Staff Product Designer on Notion's Core team, you will design elegant, flexible tools that empower people to organize their work and life. You'll tackle deep information architecture challenges, craft keyboard-first and spatial interactions, and partner closely with engineers to deliver pixel-perfect craft.",
    match: {
      score: 94,
      matching_skills: ["Information Architecture", "Design Systems", "Framer", "Design Thinking", "React & Tailwind CSS"],
      explanation: "High alignment with information architecture expertise and complex software simplification.",
      eligibility_note: "Verified work authorization and timezone overlap confirmed."
    },
    eligibility: {
      status: "Eligible",
      reasons: ["94% skill overlap", "Extensive information architecture portfolio", "Remote-first culture fit"]
    },
    tailored_doc: {
      summary: "Staff Product Designer dedicated to crafting intuitive, modular, and keyboard-friendly productivity tools.",
      highlights: [
        "Structured modular component models and complex nested navigation architectures.",
        "Collaborated with engineering on React and CSS design token parity.",
        "Champion of minimalist UI patterns with high information density."
      ]
    }
  },
  {
    id: 104,
    title: "Senior UX Researcher & Designer",
    company: "Airbnb",
    location: "Remote (APAC / India)",
    work_mode: "Remote",
    job_type: "Full Time",
    salary_min: 3600000,
    salary_max: 4800000,
    salary_currency: "INR",
    posted_at: new Date(Date.now() - 36 * 3600000).toISOString(),
    discovered_at: new Date(Date.now() - 20 * 3600000).toISOString(),
    source: "Jobicy",
    url: "https://airbnb.com/careers",
    description:
      "Join Airbnb's Guest Experience design team to conduct mixed-methods user research and translate qualitative behavioral insights into high-impact mobile and web product experiences. You will design prototypes, run unmoderated user tests, and align stakeholders on user journey maps.",
    match: {
      score: 91,
      matching_skills: ["User Research & Usability Testing", "Wireframing & Prototyping", "Figma", "Design Thinking"],
      explanation: "Strong background in usability testing, Nielsen Norman Group certification, and consumer empathy.",
      eligibility_note: "NN/g UX Master certification provides exceptional credibility."
    },
    eligibility: {
      status: "Eligible",
      reasons: ["91% skill overlap", "NN/g UX Master certified", "Experience across mobile and web"]
    },
    tailored_doc: {
      summary: "Senior UX Researcher & Designer with NN/g Master certification and proven success driving conversion via user testing.",
      highlights: [
        "Conducted over 50 moderated usability tests and synthesized actionable design recommendations.",
        "Facilitated enterprise design thinking workshops aligning cross-functional product teams.",
        "Created end-to-end customer journey maps identifying high-dropoff checkout steps."
      ]
    }
  },
  {
    id: 105,
    title: "Principal Product Designer - Mobile & Web",
    company: "Canva",
    location: "Remote (Global)",
    work_mode: "Remote",
    job_type: "Full Time",
    salary_min: 4500000,
    salary_max: 6200000,
    salary_currency: "INR",
    posted_at: new Date(Date.now() - 48 * 3600000).toISOString(),
    discovered_at: new Date(Date.now() - 30 * 3600000).toISOString(),
    source: "RemoteOK",
    url: "https://canva.com/careers",
    description:
      "Canva is on a mission to empower everyone in the world to design. As Principal Product Designer, you will lead interaction design and creative tool experiences, building seamless generative AI workflows, fluid canvas manipulators, and responsive web components.",
    match: {
      score: 89,
      matching_skills: ["Micro-interactions", "Interaction Design", "Figma", "Design Systems"],
      explanation: "Good fit for interaction design and creative canvas workflows; candidate's design token mastery aligns.",
      eligibility_note: "Experience level matches; requires strong visual craft portfolio."
    },
    eligibility: {
      status: "Eligible",
      reasons: ["89% skill overlap", "6+ years design experience", "Portfolio demonstrates creative excellence"]
    },
    tailored_doc: {
      summary: "Principal Product Designer specializing in creative software, micro-interactions, and visual storytelling.",
      highlights: [
        "Designed fluid canvas editing tools with sub-60ms interaction latency in prototypes.",
        "Governed interaction specs and micro-animations for web and tablet viewports.",
        "Mentored 6 junior and mid-level designers in visual craft and system thinking."
      ]
    }
  },
  {
    id: 106,
    title: "Product Designer - Design Systems & Web",
    company: "Vercel",
    location: "Remote",
    work_mode: "Remote",
    job_type: "Full Time",
    salary_min: 3900000,
    salary_max: 5400000,
    salary_currency: "INR",
    posted_at: new Date(Date.now() - 60 * 3600000).toISOString(),
    discovered_at: new Date(Date.now() - 40 * 3600000).toISOString(),
    source: "Greenhouse",
    url: "https://vercel.com/careers",
    description:
      "Vercel is looking for a Product Designer to enhance the developer dashboard, Geist design system, and deployment workflows. You'll bridge design and frontend engineering with React, Tailwind CSS, and Figma tokens to create blisteringly fast, elegant interfaces.",
    match: {
      score: 87,
      matching_skills: ["Design Tokens", "React & Tailwind CSS", "Accessibility (WCAG AA)", "Figma"],
      explanation: "Candidate knows React, Tailwind CSS, and design tokens, forming a rare design-engineer bridge.",
      eligibility_note: "Strong developer empathy and component token expertise."
    },
    eligibility: {
      status: "Eligible",
      reasons: ["87% skill overlap", "Familiarity with modern React and Tailwind", "Design token architecture proficiency"]
    },
    tailored_doc: {
      summary: "Product Designer bridging the gap between Figma design systems and production React / Tailwind CSS components.",
      highlights: [
        "Built and maintained token architecture synchronized directly into CSS custom properties.",
        "Audited enterprise web apps to ensure 100% WCAG AA color contrast and screen reader accessibility.",
        "Authored comprehensive documentation guidelines for developer self-serve implementation."
      ]
    }
  }
];

export const DEMO_APPLICATIONS = [
  {
    id: 1,
    job_id: 101,
    title: "Senior Product Designer - Design Systems",
    company: "Stripe",
    location: "Remote (Global / APAC)",
    status: "Interview Scheduled",
    match_score: 98,
    url: "https://stripe.com/jobs",
    applied_at: new Date(Date.now() - 2 * 86400000).toISOString()
  },
  {
    id: 2,
    job_id: 102,
    title: "Lead UI/UX Designer - B2B SaaS",
    company: "Figma",
    location: "Hyderabad, India / Remote",
    status: "Form Prepared",
    match_score: 96,
    url: "https://figma.com/careers",
    applied_at: new Date(Date.now() - 1 * 86400000).toISOString()
  },
  {
    id: 3,
    job_id: 103,
    title: "Staff Product Designer - Core Experience",
    company: "Notion",
    location: "Remote (India / Global)",
    status: "Matched",
    match_score: 94,
    url: "https://notion.so/careers",
    applied_at: new Date(Date.now() - 12 * 3600000).toISOString()
  }
];

export const DEMO_SOURCE_REPORT = {
  checked: 7,
  duplicate_listings_removed: 18,
  locations: ["Hyderabad, India", "Bengaluru, India", "Remote (Global)"],
  remote_allowed: true,
  salary_filter_applied: true,
  experience_filter_applied: true,
  sources: [
    {
      source: "Greenhouse Connectors",
      status: "ok",
      coverage: "Direct employer boards (Stripe, Vercel, Figma)",
      queries: [
        { query: "Product Design", status: "ok", available: 14, matched: 4, role_filtered: 10, http_status: 200 }
      ]
    },
    {
      source: "Lever Public Boards",
      status: "ok",
      coverage: "Verified public Lever career feeds",
      queries: [
        { query: "UI/UX Designer", status: "ok", available: 9, matched: 2, role_filtered: 7, http_status: 200 }
      ]
    },
    {
      source: "Remotive Remote API",
      status: "ok",
      coverage: "Curated design & tech remote vacancies",
      queries: [
        { query: "Design Systems", status: "ok", available: 12, matched: 3, role_filtered: 9, http_status: 200 }
      ]
    },
    {
      source: "Jobicy API",
      status: "ok",
      coverage: "Global remote design jobs feed",
      queries: [
        { query: "UX Research", status: "ok", available: 8, matched: 1, role_filtered: 7, http_status: 200 }
      ]
    },
    {
      source: "RemoteOK Feed",
      status: "ok",
      coverage: "Verified remote-friendly tech roles",
      queries: [
        { query: "Interaction Designer", status: "ok", available: 11, matched: 2, role_filtered: 9, http_status: 200 }
      ]
    }
  ]
};

export const DEMO_STATS = {
  discovered_today: 14,
  published_24h: 8,
  eligible: 12,
  submitted: 3,
  failed: 0,
  average_match: 94
};

export const DEMO_AUTOMATION_STATE = {
  runs: [
    { id: 418, status: "COMPLETED", started_at: "Today 09:00 AM", summary: "Discovered 14 vacancies, 3 prepared for review" },
    { id: 417, status: "COMPLETED", started_at: "Yesterday 09:00 AM", summary: "Discovered 11 vacancies, 2 prepared for review" }
  ],
  events: [
    { id: 1, event_type: "DAILY_DISCOVERY_COMPLETED", created_at: new Date(Date.now() - 3600000).toISOString() },
    { id: 2, event_type: "ELIGIBILITY_AUDIT_PASSED", created_at: new Date(Date.now() - 7200000).toISOString() },
    { id: 3, event_type: "EMERGENCY_STOP_HEALTHY", created_at: new Date(Date.now() - 14400000).toISOString() }
  ],
  submissions_allowed_by_environment: true,
  config: {
    config_json: JSON.stringify({
      daily_limit: 10,
      company_limit: 2,
      minimum_score: 75,
      allowed_sources: ["Greenhouse", "Lever", "Remotive", "Jobicy", "RemoteOK"]
    }),
    enabled: true,
    submissions_enabled: false,
    schedule_enabled: true,
    schedule_time: "09:00"
  }
};
