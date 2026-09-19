export function escapeTex(input: unknown): string {
  if (input === null || input === undefined) return "";
  const map: Record<string, string> = {
    "\\": "\\textbackslash{}",
    "{": "\\{",
    "}": "\\}",
    $: "\\$",
    "&": "\\&",
    "#": "\\#",
    _: "\\_",
    "%": "\\%",
    "~": "\\textasciitilde{}",
    "^": "\\textasciicircum{}",
  };
  return String(input).replace(/[\\{}$&#_%~^]/g, (c) => map[c]);
}

const MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."];
export function formatResumeDate(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = String(value).trim();
  if (!s) return "";
  if (/^(present|current|now|ongoing)$/i.test(s)) return "Present";
  const m = s.match(/^(\d{4})-(\d{1,2})/);
  if (m) {
    const mi = Number(m[2]);
    return mi >= 1 && mi <= 12 ? `${MONTHS[mi - 1]} ${m[1]}` : m[1];
  }
  return s;
}
function dateRange(start: unknown, end: unknown): string {
  const a = formatResumeDate(start);
  const b = formatResumeDate(end);
  if (a && b) return `${a} -- ${b}`;
  return a || b;
}

function urlParts(raw: string): { href: string; shown: string } {
  const href = /^(https?:|mailto:)/i.test(raw) ? raw : `https://${raw}`;
  const shown = href.replace(/^https?:\/\/(www\.)?/i, "").replace(/\/$/, "");
  return { href: href.replace(/([%#])/g, "\\$1"), shown };
}

function link(raw: string): string {
  const { href, shown } = urlParts(raw);
  return `\\href{${href}}{\\underline{${escapeTex(shown)}}}`;
}

const SKILL_GROUPS: [label: string, test: RegExp][] = [
  [
    "Languages",
    /^(python|java|javascript|typescript|c\+\+|c#|c|go|golang|rust|kotlin|swift|ruby|php|scala|sql|bash|shell|r|html|css|html\/css|dart|matlab|solidity)$/i,
  ],
  [
    "Frameworks \\& Libraries",
    /^(react|react\.js|next\.js|nextjs|node\.js|nodejs|express|express\.js|fastapi|flask|django|spring|spring boot|angular|vue|vue\.js|svelte|tailwind|tailwind css|redux|pytorch|tensorflow|keras|scikit-learn|sklearn|pandas|numpy|pytest|jest|junit|\.net|graphql)$/i,
  ],
  [
    "Cloud \\& Databases",
    /^((aws|amazon|azure|gcp|google cloud)\b.*|lambda|api gateway|dynamodb|s3|cognito|cloudwatch|cloudformation|iam|sqs|sns|postgres(ql)?|mysql|mongodb|redis|sqlite|firebase|supabase|kafka|elasticsearch|snowflake)$/i,
  ],
  [
    "Developer Tools",
    /^(git|github|gitlab|github actions|docker|kubernetes|terraform|ansible|jenkins|linux|ci\/cd|postman|vs code|vim|jira|figma|rest|rest apis?|apis?|microservices|aws sam|sam)$/i,
  ],
];

function groupSkills(names: string[]): { label: string; items: string[] }[] {
  const buckets = new Map<string, string[]>();
  for (const [label] of SKILL_GROUPS) buckets.set(label, []);
  buckets.set("Other", []);
  for (const n of names) {
    const hit = SKILL_GROUPS.find(([, re]) => re.test(n.trim()));
    buckets.get(hit ? hit[0] : "Other")!.push(n);
  }
  const groups = [...buckets.entries()].filter(([, v]) => v.length).map(([label, items]) => ({ label, items }));
  // A lone bucket (e.g. everything unrecognised) reads better as one plain line.
  if (groups.length === 1) return [{ label: "Skills", items: groups[0].items }];
  return groups;
}

const PREAMBLE = String.raw`%-------------------------
% Resume in Latex
% Author : Jake Gutierrez
% Based off of: https://github.com/sb2nov/resume
% License : MIT
%------------------------

\documentclass[a4paper,11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\usepackage[T1]{fontenc}
\input{glyphtounicode}

\pagestyle{fancy}
\fancyhf{} % clear all header and footer fields
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

% Adjust margins
\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}

\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

% Sections formatting
\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]

% Ensure that generated pdf is machine readable/ATS parsable
\pdfgentounicode=1

%-------------------------
% Custom commands
\newcommand{\resumeItem}[1]{
  \item\small{
    {#1 \vspace{-2pt}}
  }
}

\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeSubSubheading}[2]{
    \item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \textit{\small#1} & \textit{\small #2} \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \small#1 & #2 \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeSubItem}[1]{\resumeItem{#1}\vspace{-4pt}}

\renewcommand\labelitemii{$\vcenter{\hbox{\tiny$\bullet$}}$}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}

%-------------------------------------------
%%%%%%  RESUME STARTS HERE  %%%%%%%%%%%%%%%%%%%%%%%%%%%%
`;

const asList = (v: unknown): any[] => (Array.isArray(v) ? v : []);
const str = (v: unknown): string => (typeof v === "string" ? v.trim() : v === null || v === undefined ? "" : String(v).trim());

function bullets(items: string[]): string {
  const clean = items.map(str).filter(Boolean);
  if (!clean.length) return "";
  return `\n        \\resumeItemListStart\n${clean.map((b) => `          \\resumeItem{${escapeTex(b)}}`).join("\n")}\n        \\resumeItemListEnd`;
}

function section(title: string, body: string): string {
  return body ? `\n\\section{${title}}\n${body}\n` : "";
}

export function buildJakeTemplate(facts: any): string {
  const f = facts || {};
  const links = f.links || {};

  // --- header: contact details on one line, profile links on a second, so a long
  // LinkedIn/GitHub URL never wraps and strands a "|" at the end of a line.
  const contact: string[] = [];
  if (str(f.phone)) contact.push(escapeTex(str(f.phone)));
  if (str(f.email)) contact.push(`\\href{mailto:${str(f.email)}}{\\underline{${escapeTex(str(f.email))}}}`);
  if (str(f.location)) contact.push(escapeTex(str(f.location)));
  const profileLinks = ["linkedin", "github", "portfolio"].filter((k) => str(links[k])).map((k) => link(str(links[k])));
  const headerLines = [contact.join(" $|$ ") || "you@example.com", profileLinks.join(" $|$ ")].filter(Boolean);
  const header = `\\begin{center}
    \\textbf{\\Huge \\scshape ${escapeTex(str(f.name) || "Your Name")}} \\\\ \\vspace{1pt}
    \\small ${headerLines.join(" \\\\\n    ")}
\\end{center}
`;

  // --- education
  const currentYear = new Date().getFullYear();
  const education = asList(f.education)
    .map((e) => {
      const year = Number(e.graduation_year);
      const when =
        dateRange(e.start, e.end) ||
        (year ? (year > currentYear ? `Expected ${year}` : String(year)) : "");
      const degree = [str(e.degree), str(e.field)].filter(Boolean).join(" in ");
      return `    \\resumeSubheading
      {${escapeTex(str(e.school))}}{${escapeTex(str(e.location))}}
      {${escapeTex(degree)}}{${escapeTex(when)}}`;
    })
    .join("\n");

  // --- experience (bullets come from the verified highlights; the raw evidence quote is
  // only a fallback so an entry is never left without a line of substance)
  const experience = asList(f.experience)
    .map((x) => {
      const hl = asList(x.highlights).map(str).filter(Boolean);
      const lines = hl.length ? hl : [str(x.evidence)];
      return `    \\resumeSubheading
      {${escapeTex(str(x.title))}}{${escapeTex(dateRange(x.start, x.end))}}
      {${escapeTex(str(x.company))}}{${escapeTex(str(x.location))}}${bullets(lines)}`;
    })
    .join("\n");

  // --- projects
  const projects = asList(f.projects)
    .map((p) => {
      const stack = asList(p.skills).map(str).filter(Boolean).join(", ");
      const title = `\\textbf{${escapeTex(str(p.name))}}${stack ? ` $|$ \\emph{${escapeTex(stack)}}` : ""}`;
      const lines = [str(p.description), ...asList(p.highlights).map(str)].filter(Boolean);
      return `      \\resumeProjectHeading
          {${title}}{${escapeTex(dateRange(p.start, p.end))}}${bullets(lines)}`;
    })
    .join("\n");

  // --- skills
  const skillNames = asList(f.skills)
    .map((s) => (typeof s === "string" ? s : s?.name))
    .map(str)
    .filter(Boolean);
  const skills = skillNames.length
    ? ` \\begin{itemize}[leftmargin=0.15in, label={}]
    \\small{\\item{
${groupSkills(skillNames)
  .map((g) => `     \\textbf{${g.label}}{: ${g.items.map(escapeTex).join(", ")}}`)
  .join(" \\\\\n")}
    }}
 \\end{itemize}`
    : "";

  const list = (body: string) => (body ? `  \\resumeSubHeadingListStart\n${body}\n  \\resumeSubHeadingListEnd` : "");

  return (
    PREAMBLE +
    `\\begin{document}

${header}` +
    section("Education", list(education)) +
    section("Experience", list(experience)) +
    section("Projects", list(projects)) +
    section("Technical Skills", skills) +
    `
\\end{document}
`
  );
}
