import Checkbox from './Checkbox';
import { Icon } from './Icons';

export function VersionBadge({ kind = 'downgrade', children }) {
  const labels = { latest: 'Latest', downgrade: 'Downgrade', installed: 'Installed', offsets: 'Offset match' };
  return <span className={`version-badge ${kind}`}><i />{children || labels[kind] || kind}</span>;
}

export function DowngradeNotice({ acknowledged = false, onAcknowledge, compact = false }) {
  return <section className={`downgrade-notice${compact ? ' compact' : ''}`} role="note">
    <span className="downgrade-notice-icon"><Icon name="alert" size={17}/></span>
    <div>
      <strong>Older Roblox build detected</strong>
      <p>Downgrading can trigger Roblox error 280 because the client is out of date. It may also increase detection or account-action risk.</p>
      <small>Recommended only when compatibility with Vellium Executor or a trusted third-party executor specifically requires this build.</small>
    </div>
    {onAcknowledge && <label className="downgrade-confirm">
      <Checkbox checked={acknowledged} onChange={onAcknowledge} ariaLabel="Acknowledge downgrade risks"/>
      <span>I understand the risks</span>
    </label>}
  </section>;
}
