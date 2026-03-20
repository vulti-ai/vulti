<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import type { Agent, ServiceCategory } from '$lib/api';
	import ServiceConnector from '../ServiceConnector.svelte';

	let { agent }: { agent: Agent } = $props();

	function getService(type: string) {
		return (agent.services ?? []).find(s => s.type === type && s.permission !== 'write');
	}

	function connect(type: string, label: string, category: ServiceCategory) {
		store.addServiceToAgent(agent.id, {
			id: crypto.randomUUID(), category, type, label,
			status: 'connected', config: {}, permission: 'read'
		});
	}

	function disconnect(type: string) {
		const svc = (agent.services ?? []).find(s => s.type === type && s.permission !== 'write');
		if (svc) store.removeServiceFromAgent(agent.id, svc.id);
	}
</script>

<div class="space-y-8">
	<!-- Communication -->
	<section class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Messages & Email</h4>
		<ServiceConnector type="gmail" label="Gmail" category="communication" description="Read emails"
			status={getService('gmail') ? 'connected' : 'disconnected'}
			onConnect={() => connect('gmail', 'Gmail', 'communication')}
			onDisconnect={() => disconnect('gmail')} />
		<ServiceConnector type="icloud_mail" label="iCloud Mail" category="communication" description="Read emails"
			status={getService('icloud_mail') ? 'connected' : 'disconnected'}
			onConnect={() => connect('icloud_mail', 'iCloud Mail', 'communication')}
			onDisconnect={() => disconnect('icloud_mail')} />
		<ServiceConnector type="whatsapp" label="WhatsApp" category="communication" description="Read messages"
			status={getService('whatsapp') ? 'connected' : 'disconnected'}
			onConnect={() => connect('whatsapp', 'WhatsApp', 'communication')}
			onDisconnect={() => disconnect('whatsapp')} />
		<ServiceConnector type="telegram" label="Telegram" category="communication" description="Read messages"
			status={getService('telegram') ? 'connected' : 'disconnected'}
			onConnect={() => connect('telegram', 'Telegram', 'communication')}
			onDisconnect={() => disconnect('telegram')} />
		<ServiceConnector type="imessage" label="iMessage" category="communication" description="Read messages"
			status={getService('imessage') ? 'connected' : 'disconnected'}
			onConnect={() => connect('imessage', 'iMessage', 'communication')}
			onDisconnect={() => disconnect('imessage')} />
		<ServiceConnector type="slack" label="Slack" category="communication" description="Read channels"
			status={getService('slack') ? 'connected' : 'disconnected'}
			onConnect={() => connect('slack', 'Slack', 'communication')}
			onDisconnect={() => disconnect('slack')} />
		<ServiceConnector type="discord" label="Discord" category="communication" description="Read channels"
			status={getService('discord') ? 'connected' : 'disconnected'}
			onConnect={() => connect('discord', 'Discord', 'communication')}
			onDisconnect={() => disconnect('discord')} />
	</section>

	<!-- Files -->
	<section class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Files & Storage</h4>
		<ServiceConnector type="gdrive" label="Google Drive" category="files" description="Read files"
			status={getService('gdrive') ? 'connected' : 'disconnected'}
			onConnect={() => connect('gdrive', 'Google Drive', 'files')}
			onDisconnect={() => disconnect('gdrive')} />
		<ServiceConnector type="icloud_drive" label="iCloud Drive" category="files" description="Read files"
			status={getService('icloud_drive') ? 'connected' : 'disconnected'}
			onConnect={() => connect('icloud_drive', 'iCloud Drive', 'files')}
			onDisconnect={() => disconnect('icloud_drive')} />
		<ServiceConnector type="dropbox" label="Dropbox" category="files" description="Read files"
			status={getService('dropbox') ? 'connected' : 'disconnected'}
			onConnect={() => connect('dropbox', 'Dropbox', 'files')}
			onDisconnect={() => disconnect('dropbox')} />
		<ServiceConnector type="local_folders" label="Local Folders" category="files" description="Read local files"
			status={getService('local_folders') ? 'connected' : 'disconnected'}
			onConnect={() => connect('local_folders', 'Local Folders', 'files')}
			onDisconnect={() => disconnect('local_folders')} />
	</section>

	<!-- Calendar & Contacts -->
	<section class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Calendar & Contacts</h4>
		<ServiceConnector type="gcalendar" label="Google Calendar" category="calendar_contacts" description="Read events"
			status={getService('gcalendar') ? 'connected' : 'disconnected'}
			onConnect={() => connect('gcalendar', 'Google Calendar', 'calendar_contacts')}
			onDisconnect={() => disconnect('gcalendar')} />
		<ServiceConnector type="icloud_calendar" label="iCloud Calendar" category="calendar_contacts" description="Read events"
			status={getService('icloud_calendar') ? 'connected' : 'disconnected'}
			onConnect={() => connect('icloud_calendar', 'iCloud Calendar', 'calendar_contacts')}
			onDisconnect={() => disconnect('icloud_calendar')} />
		<ServiceConnector type="gcontacts" label="Google Contacts" category="calendar_contacts" description="Read contacts"
			status={getService('gcontacts') ? 'connected' : 'disconnected'}
			onConnect={() => connect('gcontacts', 'Google Contacts', 'calendar_contacts')}
			onDisconnect={() => disconnect('gcontacts')} />
		<ServiceConnector type="icloud_contacts" label="iCloud Contacts" category="calendar_contacts" description="Read contacts"
			status={getService('icloud_contacts') ? 'connected' : 'disconnected'}
			onConnect={() => connect('icloud_contacts', 'iCloud Contacts', 'calendar_contacts')}
			onDisconnect={() => disconnect('icloud_contacts')} />
	</section>

	<!-- Knowledge -->
	<section class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Knowledge</h4>
		<ServiceConnector type="apple_notes" label="Apple Notes" category="knowledge" description="Read notes"
			status={getService('apple_notes') ? 'connected' : 'disconnected'}
			onConnect={() => connect('apple_notes', 'Apple Notes', 'knowledge')}
			onDisconnect={() => disconnect('apple_notes')} />
		<ServiceConnector type="notion" label="Notion" category="knowledge" description="Read pages"
			status={getService('notion') ? 'connected' : 'disconnected'}
			onConnect={() => connect('notion', 'Notion', 'knowledge')}
			onDisconnect={() => disconnect('notion')} />
		<ServiceConnector type="obsidian" label="Obsidian" category="knowledge" description="Read vault"
			status={getService('obsidian') ? 'connected' : 'disconnected'}
			onConnect={() => connect('obsidian', 'Obsidian', 'knowledge')}
			onDisconnect={() => disconnect('obsidian')} />
		<ServiceConnector type="web_search" label="Web Search" category="knowledge" description="Search the web"
			status={getService('web_search') ? 'connected' : 'disconnected'}
			onConnect={() => connect('web_search', 'Web Search', 'knowledge')}
			onDisconnect={() => disconnect('web_search')} />
	</section>

	<!-- Code -->
	<section class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Code</h4>
		<ServiceConnector type="github" label="GitHub" category="code" description="Read repos & issues"
			status={getService('github') ? 'connected' : 'disconnected'}
			onConnect={() => connect('github', 'GitHub', 'code')}
			onDisconnect={() => disconnect('github')} />
		<ServiceConnector type="gitlab" label="GitLab" category="code" description="Read repos & issues"
			status={getService('gitlab') ? 'connected' : 'disconnected'}
			onConnect={() => connect('gitlab', 'GitLab', 'code')}
			onDisconnect={() => disconnect('gitlab')} />
	</section>

	<!-- Other -->
	<section class="space-y-3">
		<h4 class="text-xs font-medium uppercase text-ink-muted">Other</h4>
		<ServiceConnector type="spotify" label="Spotify" category="other" description="Read playback"
			status={getService('spotify') ? 'connected' : 'disconnected'}
			onConnect={() => connect('spotify', 'Spotify', 'other')}
			onDisconnect={() => disconnect('spotify')} />
		<ServiceConnector type="homekit" label="HomeKit" category="other" description="Read device state"
			status={getService('homekit') ? 'connected' : 'disconnected'}
			onConnect={() => connect('homekit', 'HomeKit', 'other')}
			onDisconnect={() => disconnect('homekit')} />
		<ServiceConnector type="home_assistant" label="Home Assistant" category="other" description="Read state"
			status={getService('home_assistant') ? 'connected' : 'disconnected'}
			onConnect={() => connect('home_assistant', 'Home Assistant', 'other')}
			onDisconnect={() => disconnect('home_assistant')} />
	</section>
</div>
