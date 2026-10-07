import type { Metadata } from 'next';
import { SourceReadiness } from '@/components/source-readiness';
export const metadata: Metadata = { title: 'Source readiness | Agency Intake Kit' };
export default function ReadinessPage() { return <SourceReadiness />; }
