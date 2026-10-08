import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { EvidenceTime } from '../evidence-time';

it('renders a readable UTC time while retaining the exact original timestamp and offset', () => {
  const value = '2026-10-07T02:30:00+02:30';
  render(<EvidenceTime value={value} />);
  const time = screen.getByText('Oct 7, 2026, 12:00:00 AM UTC');
  expect(time).toHaveAttribute('datetime', value);
  expect(time).toHaveAttribute('title', value);
});
it('preserves unsupported evidence rather than inventing a timestamp', () => {
  render(<EvidenceTime value="Not supplied" />);
  expect(screen.getByText('Not supplied').tagName).toBe('SPAN');
});
