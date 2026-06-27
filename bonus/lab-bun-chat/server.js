// ============================================================
// Bonus Lab: Bun Chat UI with Ollama + Memory
// RACE Framework Edition — build & test prompts live
// ============================================================

const OLLAMA_URL = "http://localhost:11434";
const MODEL = "llama3.2:3b";
const PORT = 3003;

// ─────────────────────────────────────────────────────────────
// Active system prompt — updated live from the RACE builder
// ─────────────────────────────────────────────────────────────
let activeSystemPrompt = `You are a network engineer assistant.

Available devices in this lab:
- spine1, spine2 (core switches, 192.168.0.11/12)
- leaf1, leaf2   (access switches, 192.168.0.21/22)

Keep answers concise and practical. When troubleshooting,
suggest specific commands the engineer could run.`;

// Conversation memory
const conversationHistory = [];

// ─────────────────────────────────────────────────────────────
// RACE example library — defined server-side as real JS
// objects, then injected into the HTML via JSON.stringify so
// the browser always receives clean, properly-escaped JSON.
// ─────────────────────────────────────────────────────────────
const RACE_EXAMPLES = {
  bgp: {
    label: "🔀 BGP Risk Analyzer",
    p: `You are a senior network engineer reviewing BGP configurations for a production service provider network.
Your task is to identify configuration risks that could cause routing instability, security issues, or operational incidents.
Success means returning evidence-based findings in the required schema without recommending unsafe production changes.`,
    e1: `Input:
router bgp 65001
 neighbor 10.0.0.1 remote-as 65002

Expected Output:
{
  "summary": "BGP peer is missing authentication and maximum-prefix protection.",
  "risk_score": 7,
  "issues": [
    { "severity": "high", "category": "security", "finding": "Missing BGP neighbor authentication", "evidence": "neighbor 10.0.0.1 remote-as 65002", "recommendation": "Add BGP neighbor authentication using the approved standard." },
    { "severity": "medium", "category": "stability", "finding": "Missing maximum-prefix limit", "evidence": "No maximum-prefix statement found", "recommendation": "Add maximum-prefix limits based on peer agreement." }
  ],
  "requires_human_approval": true,
  "safe_to_auto_remediate": false
}

Input:
router bgp 65001
 neighbor 10.0.0.1 remote-as 65002
 neighbor 10.0.0.1 password configured
 neighbor 10.0.0.1 maximum-prefix 5000 90

Expected Output:
{
  "summary": "BGP peer meets baseline policy.",
  "risk_score": 1,
  "issues": [],
  "requires_human_approval": false,
  "safe_to_auto_remediate": false
}`,
    n: `Context:
- Platform: Cisco IOS-XE
- All eBGP peers require authentication
- All eBGP peers require maximum-prefix limits
- This is production
- Recommendations must be safe for change review

Do NOT:
- Recommend IOS-XR syntax
- Recommend immediate production changes
- Recommend clearing BGP sessions
- Guess missing peer policy values
- Claim the configuration was changed`,
    e2: `Return structured JSON with:
- summary
- risk_score (1-10)
- issues array (severity, category, finding, evidence, recommendation)
- requires_human_approval (boolean)
- safe_to_auto_remediate (boolean)

Keep response under 400 words.`,
  },

  alert: {
    label: "🚨 Alert Triage",
    p: `You are a NOC engineer triaging network alerts.
Your task is to classify the alert, identify likely impact, recommend immediate checks, and decide whether escalation is required.
Success means routing the alert to the right next step without recommending configuration changes during triage.`,
    e1: `Input:
Interface Ethernet1 is down on CORE-RTR-01

Expected Output:
{
  "severity": "critical",
  "priority": 1,
  "impact": "Potential production traffic impact on core router",
  "immediate_checks": ["show interface Ethernet1", "show logging | include Ethernet1", "show ip route summary"],
  "escalate": true,
  "route_to": "network_oncall",
  "requires_human_approval": true
}

Input:
Interface Ethernet48 is down on ACCESS-SW-22

Expected Output:
{
  "severity": "low",
  "priority": 4,
  "impact": "Likely single access port impact",
  "immediate_checks": ["show interface Ethernet48", "check connected endpoint inventory"],
  "escalate": false,
  "route_to": "service_desk",
  "requires_human_approval": false
}`,
    n: `Context:
- Devices starting with CORE are critical infrastructure
- Devices starting with ACCESS are edge/access switches
- Critical alerts after hours must page on-call
- Low severity access port alerts should become tickets
- Business hours are 8 AM to 6 PM Eastern

Do NOT:
- Recommend rebooting a device
- Recommend configuration changes during triage
- Escalate low-priority alerts unless multiple related alerts exist
- Claim customer impact unless provided by monitoring data`,
    e2: `Return structured JSON with:
- severity (critical/high/medium/low)
- priority (1-4)
- impact
- immediate_checks (array)
- escalate (boolean)
- route_to
- requires_human_approval (boolean)`,
  },

  netbox: {
    label: "📦 NetBox Validator",
    p: `You are a NetOps automation engineer validating device configuration against NetBox source-of-truth data.
Your task is to identify drift between intended state and observed device configuration.
Success means identifying drift without assuming the device or NetBox should be changed automatically.`,
    e1: `Input:
Intent: VLAN 120 SERVER_BACKEND 10.120.0.0/24
Observed:
vlan 120
 name SERVER_BACKEND
interface Vlan120
 ip address 10.120.0.1 255.255.255.0

Expected Output:
{ "drift_detected": false, "findings": [], "recommended_action": "No action required", "requires_change_request": false }

Input:
Intent: VLAN 120 SERVER_BACKEND 10.120.0.0/24
Observed:
vlan 120
 name SERVER-BACKEND

Expected Output:
{
  "drift_detected": true,
  "findings": [
    { "severity": "medium", "type": "naming_drift", "intent": "SERVER_BACKEND", "observed": "SERVER-BACKEND", "recommendation": "Update VLAN name to match NetBox standard after approval." },
    { "severity": "high", "type": "missing_svi", "intent": "interface Vlan120 with 10.120.0.1/24", "observed": "No SVI found", "recommendation": "Create SVI only after change approval and dependency validation." }
  ],
  "recommended_action": "Open change request",
  "requires_change_request": true
}`,
    n: `Context:
- NetBox is the source of truth
- Device configuration is observed state
- VLAN names must use uppercase and underscores
- Missing SVIs require change approval
- This workflow detects drift only

Do NOT:
- Generate configuration unless requested
- Assume NetBox is wrong
- Auto-remediate production drift
- Recommend deleting existing VLANs
- Treat naming drift as a production outage`,
    e2: `Return structured JSON with:
- drift_detected (boolean)
- findings (array with severity, type, intent, observed, recommendation)
- recommended_action
- requires_change_request (boolean)`,
  },

  firewall: {
    label: "🔥 Firewall Review",
    p: `You are a network security engineer reviewing firewall policy for risky access rules.
Your task is to identify overly permissive rules, missing logging, risky source/destination combinations, and rules that may violate least privilege.
Success means identifying review-worthy risk without making unsupported assumptions about business justification.`,
    e1: `Input:
access-list OUTSIDE_IN permit ip any any

Expected Output:
{
  "risk_level": "critical",
  "finding": "Any-to-any inbound access rule",
  "why_it_matters": "This violates least privilege and may expose internal services.",
  "recommendation": "Replace with explicit source, destination, and service-based rules after dependency review.",
  "requires_review": true,
  "safe_to_auto_change": false
}

Input:
access-list OUTSIDE_IN permit tcp 203.0.113.10 host 10.1.10.5 eq 443 log

Expected Output:
{
  "risk_level": "low",
  "finding": "Specific HTTPS access rule with logging enabled",
  "why_it_matters": "Rule is scoped to a specific source, destination, and service.",
  "recommendation": "No immediate action required.",
  "requires_review": false,
  "safe_to_auto_change": false
}`,
    n: `Context:
- Inbound internet rules must be explicit
- Any-to-any rules are prohibited
- Logging is required on internet-facing permit rules
- This is a review workflow, not an enforcement workflow

Do NOT:
- Recommend deleting rules without dependency analysis
- Assume business justification is missing
- Recommend emergency changes unless risk is critical
- Generate vendor-specific commands
- Claim a rule is unused unless usage data is provided`,
    e2: `Return structured JSON with:
- risk_level (critical/high/medium/low)
- finding
- why_it_matters
- recommendation
- requires_review (boolean)
- safe_to_auto_change (boolean)`,
  },

  change: {
    label: "📋 Change Planner",
    p: `You are a network change planning assistant.
Your task is to create a safe, reviewable change plan based on the approved remediation recommendation.
Success means producing a plan that includes pre-checks, implementation steps, rollback, post-checks, risk notes, and approval status.`,
    e1: `Input:
Issue: Missing maximum-prefix on eBGP neighbor 10.0.0.1
Platform: Cisco IOS-XE
Approved recommendation: Add maximum-prefix 5000 90

Expected Output:
{
  "change_summary": "Add maximum-prefix protection to eBGP neighbor 10.0.0.1",
  "risk_level": "medium",
  "pre_checks": ["show ip bgp summary", "show run | section router bgp", "confirm peer accepted prefix limit"],
  "implementation_steps": ["Enter BGP configuration mode", "Apply maximum-prefix setting to neighbor", "Save configuration after validation"],
  "rollback_plan": ["Remove maximum-prefix statement from neighbor", "Validate BGP session remains established"],
  "post_checks": ["show ip bgp summary", "show logging | include BGP", "confirm prefixes received are below threshold"],
  "requires_human_approval": true,
  "execution_allowed": false
}`,
    n: `Context:
- All production changes require approval
- Change plans must include pre-checks, implementation steps, rollback, and post-checks
- Do not include secrets or passwords
- Do not execute changes

Do NOT:
- Claim the change has been applied
- Skip rollback steps
- Recommend clearing BGP sessions
- Include exact passwords or secrets
- Convert the plan into live commands unless explicitly requested`,
    e2: `Return structured JSON with:
- change_summary
- risk_level
- pre_checks (array)
- implementation_steps (array)
- rollback_plan (array)
- post_checks (array)
- requires_human_approval (boolean)
- execution_allowed (boolean)`,
  },

  docs: {
    label: "📝 Doc Extractor",
    p: `You are a network documentation assistant.
Your task is to extract important operational details from a router configuration and return them in a clean Markdown table.
Success means extracting only documented facts from the provided configuration.`,
    e1: `Input:
interface GigabitEthernet0/0
 description WAN to ISP-A
 ip address 203.0.113.2 255.255.255.252

Expected Output:
| Section | Value |
|---|---|
| Interface | GigabitEthernet0/0 |
| Description | WAN to ISP-A |
| IP Address | 203.0.113.2/30 |
| Role | WAN |`,
    n: `Context:
- WAN interfaces usually include ISP, WAN, MPLS, DIA, or Internet in the description
- LAN interfaces usually include Users, Servers, Voice, Wireless, or Campus
- Return only documented values from the config
- If a value is missing, write "Not found"

Do NOT:
- Invent missing descriptions
- Guess circuit IDs
- Include secrets, passwords, SNMP communities, or keys`,
    e2: `Return a Markdown table with columns: Section | Value
Extract all interface, routing, and policy details present in the config.
If a field is missing from the config, write "Not found".`,
  },

  incident: {
    label: "⚡ Incident Summary",
    p: `You are an incident communications assistant for a network operations team.
Your task is to summarize the incident using only the provided alert, ticket, and timeline data.
Success means creating a clear, calm, factual summary that works for technical and business stakeholders.`,
    e1: `Input:
Alert: CORE-RTR-01 interface Ethernet1 down at 02:14
Timeline:
02:14 alert triggered
02:17 on-call acknowledged
02:21 link restored
02:25 monitoring cleared

Expected Output:
{
  "executive_summary": "A core router interface outage was detected and restored within 11 minutes.",
  "customer_impact": "Potential brief connectivity degradation for dependent services.",
  "timeline": [
    "02:14 - Alert triggered for CORE-RTR-01 Ethernet1",
    "02:17 - On-call engineer acknowledged the alert",
    "02:21 - Link restored",
    "02:25 - Monitoring cleared"
  ],
  "next_steps": ["Review interface logs", "Confirm physical layer stability", "Determine whether provider follow-up is required"],
  "confidence": "medium"
}`,
    n: `Context:
- Audience may include technical leaders and business stakeholders
- Keep summary factual and calm
- Include only information provided
- Separate confirmed facts from assumptions

Do NOT:
- Assign blame
- Invent root cause
- Claim customer impact unless provided
- Use dramatic language`,
    e2: `Return structured JSON with:
- executive_summary
- customer_impact
- timeline (array)
- next_steps (array)
- confidence (high/medium/low)`,
  },
};


// ─────────────────────────────────────────────────────────────
// Chat handler
// ─────────────────────────────────────────────────────────────
async function handleChat(req) {
  let body;
  try { body = await req.json(); }
  catch { return Response.json({ error: "Invalid JSON body" }, { status: 400 }); }

  const userMessage = body.message?.trim();
  if (!userMessage) return Response.json({ error: "No message provided" }, { status: 400 });

  conversationHistory.push({ role: "user", content: userMessage });

  const ollamaRes = await fetch(`${OLLAMA_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MODEL,
      stream: false,
      messages: [
        { role: "system", content: activeSystemPrompt },
        ...conversationHistory,
      ],
    }),
  });
  const data = await ollamaRes.json();

  const reply = data.message?.content ?? "No response from model.";
  conversationHistory.push({ role: "assistant", content: reply });
  return Response.json({ reply, historyLength: conversationHistory.length });
}


// ─────────────────────────────────────────────────────────────
// Bun HTTP server
// ─────────────────────────────────────────────────────────────
const handler = {
  async fetch(req) {
    const { pathname } = new URL(req.url);

    if (pathname === "/" && req.method === "GET") {
      return new Response(HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
    }

    if (pathname === "/api/chat" && req.method === "POST") {
      try {
        return await handleChat(req);
      } catch (err) {
        const msg = err.message?.includes("ECONNREFUSED")
          ? "Cannot reach Ollama — is it running? Try: ollama serve"
          : "Server error: " + err.message;
        return Response.json({ error: msg }, { status: 500 });
      }
    }

    // Update system prompt from the RACE builder
    if (pathname === "/api/config" && req.method === "POST") {
      const body = await req.json();
      if (body.systemPrompt !== undefined) {
        activeSystemPrompt = body.systemPrompt;
        conversationHistory.length = 0; // reset memory when prompt changes
      }
      return Response.json({ ok: true, systemPrompt: activeSystemPrompt });
    }

    // Reset conversation only
    if (pathname === "/api/examples" && req.method === "GET") {
      return Response.json(RACE_EXAMPLES);
    }

    if (pathname === "/api/reset" && req.method === "POST") {
      conversationHistory.length = 0;
      return Response.json({ ok: true });
    }

    // Return current config (so the UI can pre-fill on load)
    if (pathname === "/api/config" && req.method === "GET") {
      return Response.json({ systemPrompt: activeSystemPrompt, model: MODEL });
    }

    return new Response("Not Found", { status: 404 });
  },
};

let server;
let port = PORT;
while (true) {
  try {
    server = Bun.serve({ port, ...handler });
    break;
  } catch (err) {
    if (err.code === "EADDRINUSE") {
      console.warn("⚠️  Port " + port + " is in use, trying " + (port + 1) + "…");
      port++;
    } else {
      throw err;
    }
  }
}

console.log("\n🚀 Chat server running  →  http://localhost:" + server.port);
console.log("🤖 Model: " + MODEL);
console.log("📡 Ollama: " + OLLAMA_URL + "\n");


// ─────────────────────────────────────────────────────────────
// RACE Chat UI
// ─────────────────────────────────────────────────────────────
const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RACE Chat Tester</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #0b0d14;
    --surface:   #131722;
    --surface2:  #1a1f2e;
    --border:    #232b3e;
    --border2:   #2d3652;
    --text:      #d4daf0;
    --muted:     #566080;
    --accent:    #4f7ef8;
    --accent-dk: #3563d6;
    --green:     #22c55e;
    --yellow:    #f59e0b;
    --red:       #ef4444;
    --p-color:   #818cf8;
    --e1-color:  #34d399;
    --n-color:   #f59e0b;
    --e2-color:  #f472b6;
  }

  html, body { height: 100%; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Top bar ── */
  .topbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 20px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    z-index: 10;
  }
  .topbar-logo {
    font-size: 0.85rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--text);
  }
  .topbar-logo span { color: var(--accent); }
  .topbar-sub {
    font-size: 0.72rem;
    color: var(--muted);
    border-left: 1px solid var(--border2);
    padding-left: 12px;
  }
  .topbar-right { margin-left: auto; display: flex; align-items: center; gap: 8px; }
  .model-chip {
    font-size: 0.7rem;
    background: var(--surface2);
    border: 1px solid var(--border2);
    border-radius: 999px;
    padding: 3px 10px;
    color: var(--muted);
  }
  .model-chip b { color: var(--accent); }

  /* ── Main layout ── */
  .layout {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* ── Left: RACE builder ── */
  .sidebar {
    width: 380px;
    min-width: 300px;
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border-right: 1px solid var(--border);
    overflow: hidden;
    flex-shrink: 0;
  }

  .sidebar-header {
    padding: 14px 16px 10px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .sidebar-header h2 {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 2px;
  }
  .sidebar-header p {
    font-size: 0.72rem;
    color: var(--muted);
    opacity: 0.7;
  }

  .RACE-sections {
    flex: 1;
    overflow-y: auto;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  /* Accordion section */
  .RACE-section { border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }

  .section-toggle {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    background: var(--surface2);
    border: none;
    cursor: pointer;
    color: var(--text);
    font-size: 0.82rem;
    font-weight: 600;
    text-align: left;
    transition: background 0.15s;
  }
  .section-toggle:hover { background: var(--border); }

  .section-letter {
    width: 22px; height: 22px;
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem;
    font-weight: 800;
    flex-shrink: 0;
  }
  .letter-p  { background: rgba(129,140,248,0.15); color: var(--p-color); }
  .letter-e1 { background: rgba(52,211,153,0.15);  color: var(--e1-color); }
  .letter-n  { background: rgba(245,158,11,0.15);  color: var(--n-color); }
  .letter-e2 { background: rgba(244,114,182,0.15); color: var(--e2-color); }

  .section-label { flex: 1; }
  .section-label small { display: block; font-size: 0.67rem; font-weight: 400; color: var(--muted); margin-top: 1px; }
  .chevron { font-size: 0.65rem; color: var(--muted); transition: transform 0.2s; }
  .RACE-section.open .chevron { transform: rotate(90deg); }

  .section-body {
    display: none;
    padding: 10px;
    background: var(--bg);
    border-top: 1px solid var(--border);
  }
  .RACE-section.open .section-body { display: block; }

  .section-body textarea {
    width: 100%;
    background: var(--surface2);
    border: 1px solid var(--border2);
    border-radius: 6px;
    color: var(--text);
    font-size: 0.78rem;
    font-family: "SF Mono", "Fira Code", monospace;
    line-height: 1.6;
    padding: 8px 10px;
    resize: vertical;
    outline: none;
    transition: border-color 0.15s;
    min-height: 90px;
  }
  .section-body textarea:focus { border-color: var(--accent); }
  .section-body textarea::placeholder { color: var(--muted); opacity: 0.6; font-style: italic; }

  .section-hint {
    margin-top: 6px;
    font-size: 0.67rem;
    color: var(--muted);
    line-height: 1.5;
  }

  /* Preview + Apply */
  .sidebar-footer {
    padding: 10px;
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex-shrink: 0;
  }

  .preview-box {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 0.68rem;
    font-family: "SF Mono", "Fira Code", monospace;
    color: var(--muted);
    max-height: 80px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
  }

  .apply-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: 100%;
    padding: 9px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 0.82rem;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.15s, transform 0.1s;
    letter-spacing: 0.02em;
  }
  .apply-btn:hover { background: var(--accent-dk); }
  .apply-btn:active { transform: scale(0.98); }
  .apply-btn.success { background: #16a34a; }

  /* ── Right: Chat ── */
  .chat-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--bg);
  }

  .chat-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 18px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .chat-header-title { font-size: 0.82rem; font-weight: 600; color: var(--text); }
  .memory-badge {
    font-size: 0.68rem;
    background: var(--surface2);
    border: 1px solid var(--border2);
    border-radius: 999px;
    padding: 2px 9px;
    color: var(--muted);
  }
  .memory-badge b { color: #38bdf8; }

  .prompt-active {
    margin-left: auto;
    font-size: 0.67rem;
    color: var(--green);
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .prompt-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px 10px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    scroll-behavior: smooth;
  }

  .msg {
    max-width: 78%;
    line-height: 1.65;
    padding: 11px 15px;
    border-radius: 14px;
    font-size: 0.88rem;
    white-space: pre-wrap;
    word-break: break-word;
    animation: fadeUp 0.18s ease;
  }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; } }

  .msg.user {
    align-self: flex-end;
    background: var(--accent);
    color: #f0f4ff;
    border-bottom-right-radius: 4px;
  }
  .msg.assistant {
    align-self: flex-start;
    background: var(--surface2);
    color: var(--text);
    border: 1px solid var(--border2);
    border-bottom-left-radius: 4px;
  }
  .msg.system-notice {
    align-self: center;
    background: rgba(245,158,11,0.08);
    border: 1px dashed rgba(245,158,11,0.3);
    color: var(--yellow);
    font-size: 0.75rem;
    border-radius: 8px;
    padding: 7px 14px;
    max-width: 90%;
    text-align: center;
  }
  .msg.error {
    align-self: flex-start;
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.3);
    color: var(--red);
    border-bottom-left-radius: 4px;
    font-size: 0.82rem;
  }

  .typing {
    align-self: flex-start;
    background: var(--surface2);
    border: 1px solid var(--border2);
    border-radius: 14px;
    border-bottom-left-radius: 4px;
    padding: 13px 16px;
    display: flex;
    gap: 5px;
    align-items: center;
  }
  .typing span {
    width: 6px; height: 6px;
    background: var(--muted);
    border-radius: 50%;
    animation: bounce 1.1s infinite ease-in-out;
  }
  .typing span:nth-child(2) { animation-delay: 0.18s; }
  .typing span:nth-child(3) { animation-delay: 0.36s; }
  @keyframes bounce {
    0%,80%,100% { transform: translateY(0); }
    40% { transform: translateY(-5px); background: var(--accent); }
  }

  .chat-footer {
    padding: 10px 18px 16px;
    display: flex;
    gap: 8px;
    border-top: 1px solid var(--border);
    flex-shrink: 0;
  }

  #input {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border2);
    border-radius: 10px;
    color: var(--text);
    font-size: 0.88rem;
    padding: 10px 14px;
    outline: none;
    resize: none;
    height: 44px;
    max-height: 140px;
    overflow-y: auto;
    font-family: inherit;
    line-height: 1.5;
    transition: border-color 0.15s;
  }
  #input:focus { border-color: var(--accent); }
  #input::placeholder { color: var(--muted); opacity: 0.7; }

  .chat-footer button {
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.82rem;
    font-weight: 600;
    height: 44px;
    transition: background 0.15s, transform 0.1s;
  }
  .chat-footer button:active { transform: scale(0.97); }
  .chat-footer button:disabled { opacity: 0.4; cursor: not-allowed; }

  #send-btn { background: var(--accent); color: #fff; padding: 0 20px; }
  #send-btn:hover:not(:disabled) { background: var(--accent-dk); }

  #reset-btn {
    background: var(--surface2);
    color: var(--muted);
    border: 1px solid var(--border2);
    padding: 0 14px;
  }
  #reset-btn:hover:not(:disabled) { color: var(--text); border-color: var(--border2); }

  /* ── Example picker ── */
  .examples-bar {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .examples-label {
    font-size: 0.67rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 5px;
  }
  .examples-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
  }
  .example-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 8px;
    cursor: pointer;
    font-size: 0.7rem;
    color: var(--muted);
    line-height: 1.3;
    transition: background 0.12s, border-color 0.12s, color 0.12s;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .example-card:hover { background: var(--border); color: var(--text); border-color: var(--border2); }
  .example-card.active { border-color: var(--accent); color: var(--accent); background: rgba(79,126,248,0.1); }
  .example-card .ci { margin-right: 4px; }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 99px; }
</style>
</head>
<body>

<!-- Top bar -->
<div class="topbar">
  <div class="topbar-logo">P<span>.</span>E<span>.</span>N<span>.</span>E<span>.</span></div>
  <div class="topbar-sub">Prompt Engineering Tester &nbsp;·&nbsp; AI Networking Workshop</div>
  <div class="topbar-right">
    <div class="model-chip">model: <b>${MODEL}</b></div>
  </div>
</div>

<!-- Main layout -->
<div class="layout">

  <!-- ── Left: RACE builder ── -->
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>Prompt Builder</h2>
      <p>Fill each section, then click Apply to test your prompt →</p>
    </div>

    <!-- Example loader -->
    <div class="examples-bar">
      <div class="examples-label">Load an example</div>
      <div class="examples-grid">
        <button class="example-card" onclick="loadExample('bgp',this)"><span class="ci">🔀</span>BGP Risk Analyzer</button>
        <button class="example-card" onclick="loadExample('alert',this)"><span class="ci">🚨</span>Alert Triage</button>
        <button class="example-card" onclick="loadExample('netbox',this)"><span class="ci">📦</span>NetBox Validator</button>
        <button class="example-card" onclick="loadExample('firewall',this)"><span class="ci">🔥</span>Firewall Review</button>
        <button class="example-card" onclick="loadExample('change',this)"><span class="ci">📋</span>Change Planner</button>
        <button class="example-card" onclick="loadExample('docs',this)"><span class="ci">📝</span>Doc Extractor</button>
        <button class="example-card" onclick="loadExample('incident',this)"><span class="ci">⚡</span>Incident Summary</button>
      </div>
    </div>

    <div class="RACE-sections">

      <!-- P: Persona & Purpose -->
      <div class="RACE-section open" id="sec-p">
        <button class="section-toggle" onclick="toggleSection('sec-p')">
          <div class="section-letter letter-p">P</div>
          <div class="section-label">
            Persona &amp; Purpose
            <small>Who is the AI and what should it do?</small>
          </div>
          <span class="chevron">&#9658;</span>
        </button>
        <div class="section-body">
          <textarea id="pane-p" rows="5" placeholder="You are a senior network security engineer reviewing firewall configs for a financial institution. Your task is to identify security risks that could lead to breaches or compliance violations."></textarea>
          <div class="section-hint">Define the role, expertise level, and specific task. This sets the AI's perspective.</div>
        </div>
      </div>

      <!-- E: Examples -->
      <div class="RACE-section open" id="sec-e1">
        <button class="section-toggle" onclick="toggleSection('sec-e1')">
          <div class="section-letter letter-e1">E</div>
          <div class="section-label">
            Examples
            <small>Show input/output pairs — at least 2</small>
          </div>
          <span class="chevron">&#9658;</span>
        </button>
        <div class="section-body">
          <textarea id="pane-e1" rows="6" placeholder="Input: access-list 101 permit ip any any&#10;Output: { &quot;severity&quot;: &quot;critical&quot;, &quot;issue&quot;: &quot;Overly permissive ACL&quot;, &quot;recommendation&quot;: &quot;Use explicit permit rules&quot; }&#10;&#10;Input: access-list 102 permit tcp 10.0.0.0 0.255.255.255 any eq 443&#10;Output: { &quot;severity&quot;: &quot;low&quot;, &quot;issue&quot;: &quot;Source could be narrower&quot;, &quot;recommendation&quot;: &quot;Narrow to specific subnets&quot; }"></textarea>
          <div class="section-hint">Input/output pairs teach the model your exact format. Include edge cases too.</div>
        </div>
      </div>

      <!-- N: kNowledge & coNstraints -->
      <div class="RACE-section open" id="sec-n">
        <button class="section-toggle" onclick="toggleSection('sec-n')">
          <div class="section-letter letter-n">N</div>
          <div class="section-label">
            kNowledge &amp; coNstraints
            <small>Context to use + boundaries to respect</small>
          </div>
          <span class="chevron">&#9658;</span>
        </button>
        <div class="section-body">
          <textarea id="pane-n" rows="6" placeholder="Context:&#10;- Production internet-facing firewall&#10;- Cisco ASA 9.16, PCI-DSS required&#10;- All permit rules must have logging enabled&#10;&#10;Do NOT:&#10;- Suggest changes without security justification&#10;- Recommend features not in ASA 9.16&#10;- Assume budget for hardware upgrades"></textarea>
          <div class="section-hint">Prevents hallucinations, keeps recommendations practical, enforces compliance.</div>
        </div>
      </div>

      <!-- E: Evaluation -->
      <div class="RACE-section open" id="sec-e2">
        <button class="section-toggle" onclick="toggleSection('sec-e2')">
          <div class="section-letter letter-e2">E</div>
          <div class="section-label">
            Evaluation &amp; Output
            <small>Format, length, and success criteria</small>
          </div>
          <span class="chevron">&#9658;</span>
        </button>
        <div class="section-body">
          <textarea id="pane-e2" rows="4" placeholder="Return a JSON array of findings. Each finding must include: severity (critical/high/medium/low), issue, and recommendation. Keep total response under 300 words."></textarea>
          <div class="section-hint">Specify the exact output format. Constraints on length prevent verbose answers.</div>
        </div>
      </div>

    </div><!-- /RACE-sections -->

    <div class="sidebar-footer">
      <div class="preview-box" id="prompt-preview">← Fill in the sections above and click Apply</div>
      <button class="apply-btn" id="apply-btn" onclick="applyPrompt()">
        ▶ &nbsp;Apply Prompt &amp; Reset Chat
      </button>
    </div>
  </div><!-- /sidebar -->

  <!-- ── Right: Chat ── -->
  <div class="chat-panel">
    <div class="chat-header">
      <div class="chat-title" style="font-size:0.82rem;font-weight:600;">Test your prompt here</div>
      <div class="memory-badge">memory: <b id="count">0</b> msgs</div>
      <div class="prompt-active" id="prompt-status" style="display:none;">
        <div class="prompt-dot"></div> Prompt active
      </div>
    </div>

    <div id="messages">
      <div class="msg system-notice">
        Build your RACE prompt on the left, then click <b>Apply</b> to start testing.
      </div>
    </div>

    <div class="chat-footer">
      <textarea id="input" placeholder="Send a test message… (Enter to send)" disabled></textarea>
      <button id="send-btn" disabled onclick="sendMessage()">Send</button>
      <button id="reset-btn" onclick="resetChat()" title="Clear chat history">Reset</button>
    </div>
  </div><!-- /chat-panel -->

</div><!-- /layout -->

<script>
  // ── RACE examples — fetched from /api/examples on load ─
  var EXAMPLES = {};

  function loadExample(key, btn) {
    var ex = EXAMPLES[key];
    if (!ex) return;
    document.getElementById('pane-p').value  = ex.p;
    document.getElementById('pane-e1').value = ex.e1;
    document.getElementById('pane-n').value  = ex.n;
    document.getElementById('pane-e2').value = ex.e2;
    updatePreview();
    document.querySelectorAll('.example-card').forEach(function(c) { c.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    ['sec-p','sec-e1','sec-n','sec-e2'].forEach(function(id) {
      document.getElementById(id).classList.add('open');
    });
  }

  // ── Accordion ──────────────────────────────────────────────
  function toggleSection(id) {
    var sec = document.getElementById(id);
    sec.classList.toggle('open');
    updatePreview();
  }

  // ── Build prompt from RACE sections ───────────────────
  function buildPrompt() {
    var p  = (document.getElementById('pane-p').value  || '').trim();
    var e1 = (document.getElementById('pane-e1').value || '').trim();
    var n  = (document.getElementById('pane-n').value  || '').trim();
    var e2 = (document.getElementById('pane-e2').value || '').trim();

    var parts = [];
    if (p)  parts.push('## PERSONA & PURPOSE\\n' + p);
    if (e1) parts.push('## EXAMPLES\\n' + e1);
    if (n)  parts.push('## KNOWLEDGE & CONSTRAINTS\\n' + n);
    if (e2) parts.push('## EVALUATION & OUTPUT\\n' + e2);

    return parts.join('\\n\\n');
  }

  function updatePreview() {
    var prompt = buildPrompt();
    var preview = document.getElementById('prompt-preview');
    preview.textContent = prompt || '← Fill in the sections above and click Apply';
  }

  // Live preview update
  ['pane-p','pane-e1','pane-n','pane-e2'].forEach(function(id) {
    document.getElementById(id).addEventListener('input', updatePreview);
  });

  // ── Apply prompt ───────────────────────────────────────────
  async function applyPrompt() {
    var prompt = buildPrompt();
    if (!prompt.trim()) {
      alert('Fill in at least one RACE section before applying.');
      return;
    }

    var btn = document.getElementById('apply-btn');
    btn.disabled = true;
    btn.textContent = 'Applying…';

    try {
      var res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ systemPrompt: prompt }),
      });
      await res.json();

      // Clear chat and enable input
      clearMessages();
      addMessage('system-notice', '✅ Prompt applied! Conversation reset. Start testing →');
      document.getElementById('count').textContent = '0';
      document.getElementById('input').disabled = false;
      document.getElementById('send-btn').disabled = false;
      document.getElementById('prompt-status').style.display = 'flex';
      document.getElementById('input').focus();

      btn.classList.add('success');
      btn.textContent = '✓  Applied!';
      setTimeout(function() {
        btn.classList.remove('success');
        btn.textContent = '▶  Apply Prompt & Reset Chat';
        btn.disabled = false;
      }, 1800);
    } catch (err) {
      alert('Error applying prompt: ' + err.message);
      btn.disabled = false;
      btn.textContent = '▶  Apply Prompt & Reset Chat';
    }
  }

  // ── Chat ───────────────────────────────────────────────────
  function clearMessages() {
    document.getElementById('messages').innerHTML = '';
  }

  function addMessage(role, text) {
    var div = document.createElement('div');
    div.className = 'msg ' + role;
    div.textContent = text;
    var el = document.getElementById('messages');
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
    return div;
  }

  function showTyping() {
    var el = document.createElement('div');
    el.className = 'typing';
    el.innerHTML = '<span></span><span></span><span></span>';
    var msgs = document.getElementById('messages');
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
    return el;
  }

  // Auto-grow textarea
  var inputEl = document.getElementById('input');
  inputEl.addEventListener('input', function() {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + 'px';
  });

  async function sendMessage() {
    var text = inputEl.value.trim();
    if (!text) return;

    inputEl.value = '';
    inputEl.style.height = '44px';
    document.getElementById('send-btn').disabled = true;

    addMessage('user', text);
    var typing = showTyping();

    try {
      var res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      var data = await res.json();
      typing.remove();

      if (data.error) {
        addMessage('error', '⚠️ ' + data.error);
      } else {
        addMessage('assistant', data.reply);
        document.getElementById('count').textContent = data.historyLength || '?';
      }
    } catch (err) {
      typing.remove();
      addMessage('error', '⚠️ Network error: ' + err.message);
    } finally {
      document.getElementById('send-btn').disabled = false;
      inputEl.focus();
    }
  }

  inputEl.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  async function resetChat() {
    await fetch('/api/reset', { method: 'POST' });
    clearMessages();
    document.getElementById('count').textContent = '0';
    addMessage('system-notice', '🔄 Chat history cleared. Prompt still active.');
  }

  // Load examples + current config on startup
  Promise.all([
    fetch('/api/examples').then(function(r) { return r.json(); }),
    fetch('/api/config').then(function(r) { return r.json(); }),
  ]).then(function(results) {
    EXAMPLES = results[0];
    var cfg   = results[1];
    if (cfg.systemPrompt) {
      document.getElementById('pane-p').value = cfg.systemPrompt;
      updatePreview();
    }
  });
</script>
</body>
</html>`;
