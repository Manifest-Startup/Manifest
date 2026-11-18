import { createElement } from 'react';
import type { IconType } from 'react-icons';
import {
  FaLinkedin,
  FaPalette,
  FaPenNib,
  FaRobot,
  FaSalesforce,
  FaSlack,
} from 'react-icons/fa6';
import {
  SiApple,
  SiAsana,
  SiBitbucket,
  SiBox,
  SiClickup,
  SiDropbox,
  SiFigma,
  SiGithub,
  SiGitlab,
  SiGoogle,
  SiGoogleanalytics,
  SiHubspot,
  SiIntercom,
  SiJira,
  SiMailchimp,
  SiMake,
  SiMeta,
  SiN8N,
  SiNotion,
  SiQuickbooks,
  SiReddit,
  SiShopify,
  SiStripe,
  SiTrello,
  SiVercel,
  SiWoo,
  SiX,
  SiXero,
  SiZapier,
  SiZendesk,
} from 'react-icons/si';

/**
 * Whether the underlying OAuth/API integration is wired end-to-end.
 *
 * - `available`: the Connect button starts the OAuth flow and the user can
 *   connect for real.
 * - `coming_soon`: the catalog row is shown for marketing visibility, but the
 *   Connect button is replaced with a non-interactive "Coming soon" badge so
 *   users do not hit `Unsupported provider` errors. Flip an entry to
 *   `available` once its backend OAuth handler ships.
 */
export type IntegrationAvailability = 'available' | 'coming_soon';

export interface IntegrationCatalogEntry {
  id: string;
  name: string;
  description: string;
  icon: IconType | null;
  category: string;
  brandColor: string;
  availability?: IntegrationAvailability;
  /** Linked and unlinked in its own Account section (not the integrations grid). */
  managedElsewhere?: boolean;
}

// Open Media's own mark (a bitmap), sized like a react-icons glyph.
const OpenMediaIcon: IconType = ({ size = '1em', className, title }) =>
  createElement('img', {
    src: '/brand/open-media-mark-light.png',
    width: size,
    height: size,
    alt: title ?? '',
    className,
    style: { borderRadius: '22%' },
  });

export const integrationCatalog: IntegrationCatalogEntry[] = [
  {
    id: 'open_media',
    name: 'Open Media',
    description: 'Messages, pitch shorts and your sign-in, across open social networks',
    icon: OpenMediaIcon,
    category: 'Social Media',
    brandColor: '#1d1d1f',
    managedElsewhere: true,
  },
  {
    id: 'google',
    name: 'Google',
    description: 'Connect Google Workspace, Gmail, Google Drive, and Google Calendar',
    icon: SiGoogle,
    category: 'Productivity',
    brandColor: '#4285F4',
  },
  {
    id: 'apple',
    name: 'Apple',
    description: 'Connect iCloud, Apple Calendar, and Apple Notes',
    icon: SiApple,
    category: 'Productivity',
    brandColor: '#000000',
  },
  {
    id: 'microsoft',
    name: 'Microsoft 365',
    description: 'Connect Microsoft Office, Teams, OneDrive, and Outlook',
    icon: null,
    category: 'Productivity',
    brandColor: '#0078D4',
  },
  {
    id: 'notion',
    name: 'Notion',
    description: 'Connect Notion for notes, docs, and workspace collaboration',
    icon: SiNotion,
    category: 'Productivity',
    brandColor: '#000000',
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Connect Slack for team communication and notifications',
    icon: FaSlack,
    category: 'Productivity',
    brandColor: '#4A154B',
  },
  {
    id: 'asana',
    name: 'Asana',
    description: 'Connect Asana for project and task management',
    icon: SiAsana,
    category: 'Productivity',
    brandColor: '#F06A6A',
  },
  {
    id: 'trello',
    name: 'Trello',
    description: 'Connect Trello for kanban-style project management',
    icon: SiTrello,
    category: 'Productivity',
    brandColor: '#0052CC',
  },
  {
    id: 'jira',
    name: 'Jira',
    description: 'Connect Jira for agile project management and issue tracking',
    icon: SiJira,
    category: 'Productivity',
    brandColor: '#0052CC',
  },
  {
    id: 'monday',
    name: 'Monday.com',
    description: 'Connect Monday.com for work management and collaboration',
    icon: null,
    category: 'Productivity',
    brandColor: '#FF0080',
  },
  {
    id: 'clickup',
    name: 'ClickUp',
    description: 'Connect ClickUp for all-in-one productivity platform',
    icon: SiClickup,
    category: 'Productivity',
    brandColor: '#7B68EE',
  },
  {
    id: 'meta',
    name: 'Meta',
    description: 'Connect Facebook, Instagram, and WhatsApp for social media integration',
    icon: SiMeta,
    category: 'Social Media',
    brandColor: '#0081FB',
  },
  {
    id: 'linkedin',
    name: 'LinkedIn',
    description: 'Connect LinkedIn for professional networking and business development',
    icon: FaLinkedin,
    category: 'Social Media',
    brandColor: '#0077B5',
  },
  {
    id: 'x',
    name: 'X (Twitter)',
    description: 'Connect X account for social media management and engagement',
    icon: SiX,
    category: 'Social Media',
    brandColor: '#000000',
  },
  {
    id: 'reddit',
    name: 'Reddit',
    description: 'Connect Reddit account for community engagement and market research',
    icon: SiReddit,
    category: 'Social Media',
    brandColor: '#FF4500',
  },
  {
    id: 'zapier',
    name: 'Zapier',
    description: 'Automate workflows and connect with 5000+ apps',
    icon: SiZapier,
    category: 'Automation',
    brandColor: '#FF4A00',
  },
  {
    id: 'n8n',
    name: 'n8n',
    description: 'Open-source workflow automation platform',
    icon: SiN8N,
    category: 'Automation',
    brandColor: '#FF6D5A',
  },
  {
    id: 'make',
    name: 'Make (Integromat)',
    description: 'Visual platform for building automated workflows',
    icon: SiMake,
    category: 'Automation',
    brandColor: '#000000',
  },
  {
    id: 'figma',
    name: 'Figma',
    description: 'Connect Figma for design collaboration and prototyping',
    icon: SiFigma,
    category: 'Design',
    brandColor: '#F24E1E',
  },
  {
    id: 'canva',
    name: 'Canva',
    description: 'Connect Canva for design assets and pitch deck creation',
    icon: FaPalette,
    category: 'Design',
    brandColor: '#00C4CC',
  },
  {
    id: 'adobe',
    name: 'Adobe Creative Cloud',
    description: 'Connect Adobe for professional design tools',
    icon: FaPenNib,
    category: 'Design',
    brandColor: '#FF0000',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'Connect OpenAI API for advanced AI features and content generation',
    icon: FaRobot,
    category: 'AI',
    brandColor: '#412991',
  },
  {
    id: 'github',
    name: 'GitHub',
    description: 'Connect GitHub for code repositories and project management',
    icon: SiGithub,
    category: 'Development',
    brandColor: '#181717',
  },
  {
    id: 'gitlab',
    name: 'GitLab',
    description: 'Connect GitLab for DevOps and project management',
    icon: SiGitlab,
    category: 'Development',
    brandColor: '#FC6D26',
  },
  {
    id: 'bitbucket',
    name: 'Bitbucket',
    description: 'Connect Bitbucket for code collaboration',
    icon: SiBitbucket,
    category: 'Development',
    brandColor: '#0052CC',
  },
  {
    id: 'vercel',
    name: 'Vercel',
    description: 'Connect Vercel for deployment and hosting',
    icon: SiVercel,
    category: 'Development',
    brandColor: '#000000',
  },
  {
    id: 'stripe',
    name: 'Stripe',
    description: 'Connect Stripe for payment processing and financial data',
    icon: SiStripe,
    category: 'Finance',
    brandColor: '#635BFF',
  },
  {
    id: 'quickbooks',
    name: 'QuickBooks',
    description: 'Connect QuickBooks for accounting and financial management',
    icon: SiQuickbooks,
    category: 'Finance',
    brandColor: '#2CA01C',
  },
  {
    id: 'xero',
    name: 'Xero',
    description: 'Connect Xero for cloud-based accounting',
    icon: SiXero,
    category: 'Finance',
    brandColor: '#13B5EA',
  },
  {
    id: 'google-analytics',
    name: 'Google Analytics',
    description: 'Connect Google Analytics for website and app analytics',
    icon: SiGoogleanalytics,
    category: 'Analytics',
    brandColor: '#F4B400',
  },
  {
    id: 'hubspot',
    name: 'HubSpot',
    description: 'Connect HubSpot for CRM, marketing, and sales automation',
    icon: SiHubspot,
    category: 'Marketing',
    brandColor: '#FF7A59',
  },
  {
    id: 'mailchimp',
    name: 'Mailchimp',
    description: 'Connect Mailchimp for email marketing and campaigns',
    icon: SiMailchimp,
    category: 'Marketing',
    brandColor: '#FFE01B',
  },
  {
    id: 'salesforce',
    name: 'Salesforce',
    description: 'Connect Salesforce for CRM and customer relationship management',
    icon: FaSalesforce,
    category: 'Marketing',
    brandColor: '#00A1E0',
  },
  {
    id: 'dropbox',
    name: 'Dropbox',
    description: 'Connect Dropbox for file storage and sharing',
    icon: SiDropbox,
    category: 'Storage',
    brandColor: '#0061FF',
  },
  {
    id: 'box',
    name: 'Box',
    description: 'Connect Box for secure file sharing and collaboration',
    icon: SiBox,
    category: 'Storage',
    brandColor: '#0061D5',
  },
  {
    id: 'docusign',
    name: 'DocuSign',
    description: 'Connect DocuSign for electronic signatures and document management',
    icon: null,
    category: 'Legal',
    brandColor: '#003DA5',
  },
  {
    id: 'hellosign',
    name: 'HelloSign',
    description: 'Connect HelloSign for e-signatures and document workflows',
    icon: null,
    category: 'Legal',
    brandColor: '#FF3C00',
  },
  {
    id: 'intercom',
    name: 'Intercom',
    description: 'Connect Intercom for customer messaging and support',
    icon: SiIntercom,
    category: 'Support',
    brandColor: '#286EFA',
  },
  {
    id: 'zendesk',
    name: 'Zendesk',
    description: 'Connect Zendesk for customer service and support ticketing',
    icon: SiZendesk,
    category: 'Support',
    brandColor: '#03363D',
  },
  {
    id: 'shopify',
    name: 'Shopify',
    description: 'Connect Shopify for e-commerce and online store management',
    icon: SiShopify,
    category: 'E-commerce',
    brandColor: '#96BF48',
  },
  {
    id: 'woocommerce',
    name: 'WooCommerce',
    description: 'Connect WooCommerce for WordPress e-commerce',
    icon: SiWoo,
    category: 'E-commerce',
    brandColor: '#96588A',
  },
];

export const integrationCategories = [
  'All',
  'Productivity',
  'Social Media',
  'Automation',
  'Design',
  'AI',
  'Development',
  'Finance',
  'Marketing',
  'Analytics',
  'Storage',
  'Legal',
  'Support',
  'E-commerce',
];

export const integrationCatalogById = integrationCatalog.reduce<Record<string, IntegrationCatalogEntry>>(
  (acc, integration) => {
    acc[integration.id] = integration;
    return acc;
  },
  {},
);

export const getIntegrationCatalogEntry = (serviceId: string) => integrationCatalogById[serviceId];

export { knownIntegrationServiceIds } from './integrationServiceIds';
