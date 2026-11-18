import React, { useEffect, useMemo, useState } from 'react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail?.errors) ? `${detail.message}: ${detail.errors.join(' ')}` : detail?.message;
    throw new Error(typeof detail === 'string' ? detail : message || JSON.stringify(detail) || `Request failed (${response.status})`);
  }
  return data;
}

function App() {
  const [services, setServices] = useState([]);
  const [attempts, setAttempts] = useState([]);
  const [metrics, setMetrics] = useState({});
  const [selectedService, setSelectedService] = useState('');
  const [versions, setVersions] = useState([]);
  const [fromId, setFromId] = useState('');
  const [toId, setToId] = useState('');
  const [comparison, setComparison] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState(null);
  const [serviceForm, setServiceForm] = useState({ name: '', role: 'provider', owner: '' });
  const [usageForm, setUsageForm] = useState({ consumer_service_id: '', provider_service_id: '', method: 'GET', path: '', sends: '', reads: '' });
  const [showAllAttempts, setShowAllAttempts] = useState(false);

  const providers = useMemo(() => services.filter((service) => service.role === 'provider'), [services]);
  const selected = providers.find((service) => String(service.id) === String(selectedService));

  async function refresh() {
    const [serviceResult, attemptResult, metricResult] = await Promise.allSettled([
      request('/api/services'), request('/api/publish-attempts'), request('/api/metrics'),
    ]);
    const failures = [];
    if (serviceResult.status === 'fulfilled') {
      const serviceData = serviceResult.value;
      setServices(serviceData);
      if (!selectedService && serviceData.some((service) => service.role === 'provider')) {
        setSelectedService(String(serviceData.find((service) => service.role === 'provider').id));
      }
    } else failures.push(`Services: ${serviceResult.reason.message}`);
    if (attemptResult.status === 'fulfilled') setAttempts(attemptResult.value);
    else failures.push(`Publish history: ${attemptResult.reason.message}`);
    if (metricResult.status === 'fulfilled') setMetrics(metricResult.value);
    else failures.push(`Metrics: ${metricResult.reason.message}`);
    setError(failures.length ? failures.join(' · ') : '');
  }

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    if (!selectedService) return;
    request(`/api/services/${selectedService}/versions`).then((data) => {
      setVersions(data);
      setFromId((current) => data.some((version) => String(version.id) === current) ? current : '');
      setToId((current) => data.some((version) => String(version.id) === current) ? current : '');
      setComparison(null);
    }).catch((err) => setError(err.message));
  }, [selectedService]);

  async function importKit() {
    setBusy(true); setError(''); setMessage('');
    try {
      await request('/api/import/starter-kit', { method: 'POST' });
      setMessage('Upload Successful');
      await refresh();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function uploadSpec(event) {
    event.preventDefault();
    if (!file || !selectedService) return;
    setBusy(true); setError(''); setMessage('');
    const form = new FormData(); form.append('file', file);
    try {
      const result = await request(`/api/services/${selectedService}/versions`, { method: 'POST', body: form });
      setMessage(`Added ${result.version} from ${result.source_filename}.`);
      setFile(null); event.target.reset();
      await refresh();
      setVersions(await request(`/api/services/${selectedService}/versions`));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function createService(event) {
    event.preventDefault(); setError(''); setMessage(''); setBusy(true);
    try {
      const result = await request('/api/services', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...serviceForm, name: serviceForm.name.trim(), owner: serviceForm.owner.trim() || null }) });
      setMessage(`Registered ${result.role} service ${result.name}.`);
      setServiceForm({ name: '', role: 'provider', owner: '' });
      await refresh();
      if (result.role === 'provider') setSelectedService(String(result.id));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function registerUsage(event) {
    event.preventDefault(); setError(''); setMessage(''); setBusy(true);
    try {
      const result = await request(`/api/services/${usageForm.consumer_service_id}/usages`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
          provider_service_id: Number(usageForm.provider_service_id), method: usageForm.method, path: usageForm.path,
          sends: usageForm.sends.split(',').map((value) => value.trim()).filter(Boolean),
          reads: usageForm.reads.split(',').map((value) => value.trim()).filter(Boolean),
        }) });
      setMessage(`Registered ${result.method} ${result.path} usage.`);
      setUsageForm((current) => ({ ...current, path: '', sends: '', reads: '' }));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function compare() {
    if (!fromId || !toId || fromId === toId) return;
    setBusy(true); setError(''); setMessage('');
    try { setComparison(await request(`/api/versions/${fromId}/compare/${toId}`)); }
    catch (err) { setError(err.message); setComparison(null); }
    finally { setBusy(false); }
  }

  async function publish() {
    if (!toId || !fromId) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await request(`/api/versions/${toId}/publish?baseline_id=${fromId}`, { method: 'POST' });
      setMessage(`${result.outcome.toUpperCase()}: ${result.reason}`);
      await refresh();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  const versionLabel = (version) => `${version.version} · ${version.source_filename || 'uploaded'}${version.version_collision ? ' · duplicate imported version' : ''}${version.validation_status === 'invalid' ? ' · INVALID' : ''}`;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">CG</div><div><b>Contract Guard</b><span>API change control</span></div></div>
      <div className="nav-label">WORKSPACE</div>
      <a className="nav-item active" href="#overview"><span>◫</span> Overview</a>
      <a className="nav-item" href="#services"><span>◈</span> Services</a>
      <a className="nav-item" href="#compare"><span>⇄</span> Compare & publish</a>
      <a className="nav-item" href="#history"><span>◷</span> Publish history</a>
      <div className="sidebar-bottom"><div className="online-dot" /> API registry <span className="connected">CONNECTED</span></div>
    </aside>

    <main className="main-content">
      <header className="topbar"><div><span className="eyebrow">PLATFORM / CONTRACTS</span><h1>API change control</h1></div></header>
      <section className="welcome-row" id="overview">
        <div><h2>Good contracts make reliable services.</h2><p>Review API changes against declared consumer usage before they ship.</p></div>
        <button className="button button-primary" onClick={importKit} disabled={busy}>{busy ? 'Working…' : '⇩  Import starter kit'}</button>
      </section>
      {message && <div className="notice success">✓ {message}</div>}
      {error && <div className="notice danger">! {error}</div>}

      <section className="metrics-grid">
        <Metric label="Publish attempts" value={metrics.publish_attempts ?? '—'} detail="Recorded outcomes" icon="↗" />
        <Metric label="Blocked" value={metrics.blocked ?? '—'} detail="Known consumer impact" icon="⊘" tone="red" />
        <Metric label="Affected consumers" value={metrics.affected_declared_consumers ?? '—'} detail="Declared usage only" icon="◉" tone="amber" />
        <Metric label="Invalid specs" value={metrics.invalid_specs ?? '—'} detail="Rejected uploads / imports" icon="⚠" tone="blue" />
      </section>

      <section className="panel" id="services">
        <div className="panel-heading"><div><div className="eyebrow">REGISTRY</div><h3>Provider services</h3></div><span className="count-pill">{providers.length} services</span></div>
        <div className="service-grid">{providers.length === 0 ? <div className="empty-state">Import the starter kit to register services and versions.</div> : providers.map((service) => <button key={service.id} className={`service-card ${String(service.id) === selectedService ? 'selected' : ''}`} onClick={() => setSelectedService(String(service.id))}>
          <div className="service-icon">{service.name.slice(0, 2).toUpperCase()}</div><div className="service-info"><b>{service.name}</b><span>{service.owner || 'Owner not set'}</span></div><span className="version-count">{service.version_count} versions</span>
        </button>)}</div>
        <details className="registry-tools"><summary>Register a service or consumer usage</summary>
          <form className="registration-form" onSubmit={createService}>
            <label>Name<input required value={serviceForm.name} onChange={(event) => setServiceForm({ ...serviceForm, name: event.target.value })} placeholder="service-name" /></label>
            <label>Role<select value={serviceForm.role} onChange={(event) => setServiceForm({ ...serviceForm, role: event.target.value })}><option value="provider">Provider</option><option value="consumer">Consumer</option></select></label>
            <label>Owner / team<input value={serviceForm.owner} onChange={(event) => setServiceForm({ ...serviceForm, owner: event.target.value })} placeholder="Team name" /></label>
            <button className="button button-secondary" disabled={busy}>Register service</button>
          </form>
          <form className="registration-form usage-form" onSubmit={registerUsage}>
            <label>Consumer<select required value={usageForm.consumer_service_id} onChange={(event) => setUsageForm({ ...usageForm, consumer_service_id: event.target.value })}><option value="">Choose consumer</option>{services.filter((service) => service.role === 'consumer').map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label>
            <label>Provider<select required value={usageForm.provider_service_id} onChange={(event) => setUsageForm({ ...usageForm, provider_service_id: event.target.value })}><option value="">Choose provider</option>{providers.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label>
            <label>Method<select value={usageForm.method} onChange={(event) => setUsageForm({ ...usageForm, method: event.target.value })}>{['GET','POST','PUT','PATCH','DELETE'].map((method) => <option key={method}>{method}</option>)}</select></label>
            <label>Path<input required value={usageForm.path} onChange={(event) => setUsageForm({ ...usageForm, path: event.target.value })} placeholder="/quotes/{id}" /></label>
            <label>Sends<input value={usageForm.sends} onChange={(event) => setUsageForm({ ...usageForm, sends: event.target.value })} placeholder="vehicle.make, rider.age" /></label>
            <label>Reads<input value={usageForm.reads} onChange={(event) => setUsageForm({ ...usageForm, reads: event.target.value })} placeholder="quoteId, premium.total" /></label>
            <button className="button button-secondary" disabled={busy}>Register usage</button>
          </form>
        </details>
      </section>

      <section className="panel" id="compare">
        <div className="panel-heading"><div><div className="eyebrow">CHANGE REVIEW</div><h3>Compare and publish</h3></div><span className="muted">Assess known consumers before release</span></div>
        <div className="controls-row">
          <label>Provider<select value={selectedService} onChange={(event) => setSelectedService(event.target.value)}><option value="">Select service</option>{providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Baseline<select value={fromId} onChange={(event) => setFromId(event.target.value)}><option value="">Choose baseline</option>{versions.filter((version) => version.validation_status === 'valid').map((version) => <option key={version.id} value={version.id}>{versionLabel(version)}</option>)}</select></label>
          <div className="arrow">→</div>
          <label>Proposed version<select value={toId} onChange={(event) => setToId(event.target.value)}><option value="">Choose proposed version</option>{versions.filter((version) => version.validation_status === 'valid').map((version) => <option key={version.id} value={version.id}>{versionLabel(version)}</option>)}</select></label>
          <button className="button button-primary compare-button" disabled={busy || !fromId || !toId || fromId === toId} onClick={compare}>Review changes</button>
        </div>
        {selected && <form className="upload-row" onSubmit={uploadSpec}><span className="upload-label">Add a proposed spec to {selected.name}</span><input type="file" accept=".yaml,.yml,.json" onChange={(event) => setFile(event.target.files?.[0] || null)} /><button className="button button-secondary" disabled={busy || !file}>Upload spec</button></form>}
        {versions.some((version) => version.version_collision) && <div className="notice warning compact">Duplicate imported version strings are kept as separate records. Choose the exact source file in the selectors; new uploads cannot reuse an existing version.</div>}
          {comparison && <div className="comparison-result">
          <div className={`decision-banner ${comparison.summary.publish_blocked ? 'blocked' : 'safe'}`}><div><b>{comparison.summary.publish_blocked ? `Publishing blocked by policy (${comparison.summary.policy_blocker_count} blocker${comparison.summary.policy_blocker_count === 1 ? '' : 's'})` : 'No declared consumer break detected'}</b><span>{comparison.summary.change_count} changes · {comparison.summary.affected_consumer_count} affected declared consumers · {comparison.summary.warning_count} warnings</span>{comparison.summary.publish_blocked && <small>Non-breaking changes can still be blocked when an expired sunset element is used by a declared consumer.</small>}</div><button className={`button ${comparison.summary.publish_blocked ? 'button-disabled' : 'button-green'}`} onClick={publish} disabled={busy}>{comparison.summary.publish_blocked ? 'Record blocked attempt' : 'Publish version'}</button></div>
          {comparison.changes.length === 0 ? <div className="empty-state">No API contract changes found.</div> : <div className="change-list">{comparison.changes.map((change, index) => <article className="change-row" key={`${change.location}-${index}`}>
            <div className={`change-icon ${change.severity === 'breaking' ? 'breaking' : 'safe-icon'}`}>{change.severity === 'breaking' ? '!' : '↗'}</div>
            <div className="change-main"><div className="change-title"><b>{change.summary}</b><span className={`tag ${change.severity === 'breaking' ? 'tag-red' : 'tag-green'}`}>{change.severity}</span>{change.publish_blocked && <span className="tag tag-red">policy blocker</span>}{change.policy_warning && <span className="tag tag-amber">sunset warning</span>}</div><code>{change.location}</code>{change.policy_reason && <div className="policy-reason">{change.policy_reason}</div>}<div className="change-values"><span>Before: {JSON.stringify(change.before)}</span><span>After: {JSON.stringify(change.after)}</span></div>
              {change.affected_consumers.length > 0 ? <div className="consumer-tags">Affects {change.affected_consumers.map((consumer) => <span key={consumer.name}>{consumer.name}</span>)}</div> : <div className="no-impact">No declared consumer usage matched this change.</div>}
            </div>
          </article>)}</div>}
        </div>}
      </section>

      <section className="panel" id="history">
        <div className="panel-heading"><div><div className="eyebrow">AUDIT TRAIL</div><h3>Recent publish attempts</h3></div><span className="count-pill">{attempts.length} recorded</span></div>
        {attempts.length === 0 ? <div className="empty-state">Publish attempts and their outcomes will appear here.</div> : <><div className="history-list">{(showAllAttempts ? attempts : attempts.slice(0, 8)).map((attempt) => <div className="history-row" key={attempt.id}><span className={`history-status ${attempt.outcome}`}>{attempt.outcome === 'blocked' ? 'BLOCKED' : 'PUBLISHED'}</span><span>Spec #{attempt.proposed_spec_id} against #{attempt.baseline_spec_id}</span><span className="history-reason">{attempt.reason}</span><time>{new Date(attempt.created_at).toLocaleString()}</time></div>)}</div>{attempts.length > 8 && <button className="button button-secondary history-more" onClick={() => setShowAllAttempts((value) => !value)}>{showAllAttempts ? 'Show recent attempts' : `Show all ${attempts.length} attempts`}</button>}</>}
      </section>
      <footer>Contract Guard · Impact reports are based on registered consumer declarations only.</footer>
    </main>
  </div>;
}

function Metric({ label, value, detail, icon, tone = 'green' }) {
  return <div className="metric-card"><div className={`metric-icon ${tone}`}>{icon}</div><div><span className="metric-label">{label}</span><strong>{value}</strong><small>{detail}</small></div></div>;
}

export default App;
