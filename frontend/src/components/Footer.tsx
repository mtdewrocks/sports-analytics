import { useLocation } from 'react-router-dom';
import { theme } from '../theme';

const CONTACT_EMAIL = 'sportsanalytics2026@gmail.com';

// The bigger, more visible treatment only shows on these two routes --
// everywhere else gets the small, quiet version so it doesn't compete with
// already-dense data pages (tables, charts, filters).
const PROMINENT_ROUTES = ['/', '/dashboard'];

export default function Footer() {
  const location = useLocation();
  const prominent = PROMINENT_ROUTES.includes(location.pathname);

  return (
    <div
      style={{
        textAlign: 'center',
        padding: prominent ? '14px 4px' : '10px 4px',
        borderTop: prominent ? `1px solid ${theme.border}` : 'none',
      }}
    >
      <span style={{ color: prominent ? theme.textSecondary : theme.textMuted, fontSize: prominent ? 13 : 11 }}>
        Questions or feedback?{' '}
        <a
          href={`mailto:${CONTACT_EMAIL}`}
          style={{ color: prominent ? theme.textSecondary : theme.textMuted, textDecoration: 'underline' }}
        >
          {CONTACT_EMAIL}
        </a>
      </span>
    </div>
  );
}
