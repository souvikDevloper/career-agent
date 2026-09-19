# Search and monitoring verification

Verified locally on 2026-09-19 against public employer endpoints. These checks
used the real source fetch, normalization, storage and filter paths, with the
fit scorer replaced by a test stub. They did not call a paid model, submit an
application, or prove deployed availability.

| Request | Employer response | Matching role titles |
| --- | --- | --- |
| Google, SWE early career roles, India | 13 rows from Google Careers with its EARLY facet | 5 software engineer roles, including YouTube |
| Microsoft, SWE early career roles, India | 3 rows using Microsoft's Entry facet | 3 software engineer roles in Hyderabad/Bangalore |

The Google roles were Search, YouTube, Payments, Google Cloud and Corp Eng.
Microsoft returned Software Engineer - II, Software Engineer II, and Software
Engineer II - AI/ML Infrastructure CoreAI. These are a dated observation;
employers can change or close postings at any time.

## Fixed behavior

- A fresh direct employer search replaces that employer's cached result set,
  including when the fresh response is empty. Old Staff or closed roles are not
  mixed into a new early-career search.
- Source errors, timeouts, unreadable payloads and valid empty searches have
  different statuses. The agent cannot turn a failed request into a confident
  claim that an employer has no vacancies.
- Software engineering requests require an appropriate role title. Descriptions
  of silicon or data-center jobs mentioning software engineers no longer qualify.
- Countries and supported city aliases are recognized even with an empty cache.
  Google Careers' YouTube listings retain their displayed employer and have a
  Google search alias.
- Microsoft requests use browser-compatible public HTTP headers, normalize SWE
  and early-career wording into query/facet fields, and paginate beyond ten rows.
  Workday direct searches paginate beyond the first twenty results, up to the
  bounded request limit. Google queries remain bounded to three result pages.
- Detail fetching and scoring use bounded batches. Scoring reserves one model
  call per job, with a 35-second call limit and a 150-second overall search
  budget. Model outages produce explicitly provisional keyword evidence.
  Extractor labels identify the configured provider/model that answered.
- A same-turn historical match lookup keeps the active employer/location filters.
  An empty or failed search cannot be replaced with unrelated old recommendations.
- Chat, MCP and finalized voice commands share watch tools for creating, listing,
  updating, pausing and resuming watches. Watch tools pass the saved search filters
  and requested cadence through to the scheduler service.

## Coverage and reporting

Google and Microsoft have on-demand direct searches; they are not exhaustive
scheduled mirrors. Configured Amazon, Workday, Greenhouse, Lever and Ashby boards
can be refreshed when their employer is named. Other configured feeds continue
to supply cached discovery; aggregator fallback depends on its configuration.
This is not a connector for every employer or a guarantee that every available
job has been enumerated.

The `searched` tool result distinguishes `live_postings`, `cached_postings`,
`searched_postings`, `matched`, `scored`, `returned`, and `freshness`. Its
`source_checks` records attempted, successful and failed source requests.
Consumers should not label the entire cached corpus as freshly checked jobs.

Regressions cover authoritative empty responses, stale senior roles, failed
sources, malformed Google payloads, YouTube aliases, Microsoft/Workday paging,
chat/voice watch arguments, scoring deadlines and provider labels.
