// Audit report page — detailed compliance report view

import { useParams } from 'react-router-dom';

export default function ReportPage() {
  const { reportId } = useParams<{ reportId?: string }>();

  return (
    <div className="placeholder-page">
      <div className="placeholder-page__icon" aria-hidden="true">
        📋
      </div>
      <h1 className="placeholder-page__title">Audit Report</h1>
      <p className="placeholder-page__subtitle">
        {reportId
          ? `Report ${reportId} — compliance scoreboard, verdict details, and hash-chain verification.`
          : 'Select or generate a compliance report to view detailed findings.'}
      </p>
    </div>
  );
}
