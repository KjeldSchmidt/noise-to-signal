"""Build fr/de Django locale catalogs (no system gettext required)."""

from __future__ import annotations

from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parents[1]
LOCALE = ROOT / "locale"

# msgid → (fr, de)
TRANSLATIONS: dict[str, tuple[str, str]] = {
    "Brief": ("Brief", "Briefing"),
    "Personal Brief": ("Brief personnel", "Persönliches Briefing"),
    "Stories": ("Histoires", "Stories"),
    "Settings": ("Paramètres", "Einstellungen"),
    "Log out": ("Se déconnecter", "Abmelden"),
    "Legal": ("Mentions légales", "Rechtliches"),
    "Privacy": ("Confidentialité", "Datenschutz"),
    "Home": ("Accueil", "Start"),
    "Personal news, filtered": (
        "L’actualité personnelle, filtrée",
        "Persönliche Nachrichten, gefiltert",
    ),
    "Subscribe generously.": ("Abonnez-vous largement.", "Großzügig abonnieren."),
    "Read selectively.": ("Lisez sélectivement.", "Selektiv lesen."),
    "Noise to Signal pulls from the feeds you choose, ranks what is likely worth your time, and learns from theme leanings and preferences you share in chat.": (
        "Noise to Signal lit les flux que vous choisissez, classe ce qui mérite votre temps, et apprend de vos préférences thématiques et de ce que vous partagez dans le chat.",
        "Noise to Signal zieht aus den Feeds Ihrer Wahl, rankt was Ihre Zeit wert ist, und lernt aus Themenneigungen und Chat-Präferenzen.",
    ),
    "Continue with Google": ("Continuer avec Google", "Mit Google fortfahren"),
    "Browse stories": ("Parcourir les histoires", "Stories durchsuchen"),
    "No passwords — sign-in is handled by Google.": (
        "Pas de mot de passe — la connexion passe par Google.",
        "Kein Passwort — die Anmeldung läuft über Google.",
    ),
    "Languages, locations, and which feeds to include. Catalog feeds are on by default for languages you enable.": (
        "Langues, lieux et flux à inclure. Les flux du catalogue sont actifs par défaut pour les langues que vous activez.",
        "Sprachen, Orte und einzubeziehende Feeds. Katalog-Feeds sind für aktivierte Sprachen standardmäßig an.",
    ),
    "Content languages": ("Langues de contenu", "Inhaltssprachen"),
    "Only stories from feeds in these languages appear in your brief and Stories.": (
        "Seules les histoires des flux dans ces langues apparaissent dans votre brief et Stories.",
        "Nur Stories aus Feeds in diesen Sprachen erscheinen in Briefing und Stories.",
    ),
    "Languages to include": ("Langues à inclure", "Einzuschließende Sprachen"),
    "Primary language": ("Langue principale", "Primärsprache"),
    "Used for the interface and for story titles and summaries when available.": (
        "Utilisée pour l’interface et pour les titres et résumés d’histoires lorsqu’ils sont disponibles.",
        "Wird für die Oberfläche und für Story-Titel/-Zusammenfassungen genutzt, sofern vorhanden.",
    ),
    "Save languages": ("Enregistrer les langues", "Sprachen speichern"),
    "Content languages updated.": (
        "Langues de contenu mises à jour.",
        "Inhaltssprachen aktualisiert.",
    ),
    "Stored preferences": ("Préférences enregistrées", "Gespeicherte Präferenzen"),
    "Free-form memories and theme leanings that shape your brief. You can review or delete them anytime. Preferences saved in brief chat can take a few minutes to show up here.": (
        "Souvenirs libres et préférences thématiques qui façonnent votre brief. Vous pouvez les consulter ou les supprimer à tout moment. Les préférences du chat peuvent mettre quelques minutes à apparaître.",
        "Freitext-Erinnerungen und Themenneigungen für Ihr Briefing. Sie können sie jederzeit einsehen oder löschen. Im Chat gespeicherte Präferenzen können einige Minuten brauchen.",
    ),
    "Show stored preferences": ("Afficher les préférences", "Gespeicherte Präferenzen anzeigen"),
    "Close": ("Fermer", "Schließen"),
    "Loading…": ("Chargement…", "Laden…"),
    "Locations of interest": ("Lieux d’intérêt", "Interessante Orte"),
    "Locations you are interested in. We will prioritize stories from these locations.": (
        "Lieux qui vous intéressent. Nous prioriserons les histoires de ces lieux.",
        "Orte, die Sie interessieren. Stories von dort werden priorisiert.",
    ),
    "remove": ("retirer", "entfernen"),
    "No locations yet.": ("Aucun lieu pour l’instant.", "Noch keine Orte."),
    "Add a location": ("Ajouter un lieu", "Ort hinzufügen"),
    "Search for a place or use your current position. Coarse city/region is enough.": (
        "Cherchez un lieu ou utilisez votre position. Une ville/région suffit.",
        "Ort suchen oder aktuelle Position nutzen. Stadt/Region reicht.",
    ),
    "Search": ("Rechercher", "Suchen"),
    "e.g. Berlin, Germany": ("ex. Berlin, Allemagne", "z. B. Berlin, Deutschland"),
    "Use current location": ("Utiliser ma position", "Aktuellen Standort nutzen"),
    "Add location": ("Ajouter le lieu", "Ort hinzufügen"),
    "Muted — suggested to re-enable": (
        "En sourdine — à réactiver",
        "Stummgeschaltet — wieder aktivieren",
    ),
    "Unmute": ("Réactiver", "Stummschaltung aufheben"),
    "Catalog feeds": ("Flux du catalogue", "Katalog-Feeds"),
    "Mute sources you never want in Personal Brief or Stories. Feeds outside your languages stay listed so you can discover them.": (
        "Coupez les sources que vous ne voulez jamais dans le brief ou Stories. Les flux hors langues restent listés pour découverte.",
        "Quellen stummschalten, die Sie nie im Briefing oder in Stories wollen. Feeds außerhalb Ihrer Sprachen bleiben sichtbar.",
    ),
    "Enable this language under Content languages to include this source.": (
        "Activez cette langue sous Langues de contenu pour inclure cette source.",
        "Aktivieren Sie diese Sprache unter Inhaltssprachen, um diese Quelle einzubeziehen.",
    ),
    "Mute": ("Couper", "Stummschalten"),
    "Add a custom RSS feed": ("Ajouter un flux RSS perso", "Eigenen RSS-Feed hinzufügen"),
    "If the URL already exists, you will be subscribed to the shared feed (or the catalog entry will be unmuted).": (
        "Si l’URL existe déjà, vous serez abonné au flux partagé (ou l’entrée catalogue sera réactivée).",
        "Existiert die URL schon, werden Sie dem gemeinsamen Feed abonniert (oder der Katalogeintrag entsperrt).",
    ),
    "Add feed": ("Ajouter le flux", "Feed hinzufügen"),
    "Your custom feeds": ("Vos flux personnalisés", "Ihre eigenen Feeds"),
    "Unsubscribe": ("Se désabonner", "Abbestellen"),
    "Feed name": ("Nom du flux", "Feed-Name"),
    "RSS URL": ("URL RSS", "RSS-URL"),
    "Site URL (optional)": ("URL du site (optionnel)", "Site-URL (optional)"),
    "A name is required for new feeds.": (
        "Un nom est requis pour les nouveaux flux.",
        "Für neue Feeds ist ein Name erforderlich.",
    ),
    "Open settings": ("Ouvrir les paramètres", "Einstellungen öffnen"),
    "No stories yet. Check Settings if feeds are muted, or wait for the next ingest.": (
        "Pas encore d’histoires. Vérifiez les Paramètres si des flux sont coupés, ou attendez le prochain ingest.",
        "Noch keine Stories. Prüfen Sie die Einstellungen bei stummgeschalteten Feeds, oder warten Sie auf den nächsten Ingest.",
    ),
    "No stories yet. Check back after the next ingest.": (
        "Pas encore d’histoires. Revenez après le prochain ingest.",
        "Noch keine Stories. Schauen Sie nach dem nächsten Ingest wieder vorbei.",
    ),
    "Important articles and story threads from your enabled feeds, ranked by impact.": (
        "Articles et fils importants de vos flux activés, classés par impact.",
        "Wichtige Artikel und Story-Threads aus Ihren aktiven Feeds, nach Impact sortiert.",
    ),
    "Important articles and story threads from your enabled feeds (%(counter)s), ranked by impact.": (
        "Articles et fils importants de vos flux activés (%(counter)s), classés par impact.",
        "Wichtige Artikel und Story-Threads aus Ihren aktiven Feeds (%(counter)s), nach Impact sortiert.",
    ),
    "Important articles and story threads from the shared catalog, ranked by impact. Sign in to mute sources and personalize your brief.": (
        "Articles et fils importants du catalogue partagé, classés par impact. Connectez-vous pour couper des sources et personnaliser votre brief.",
        "Wichtige Artikel und Story-Threads aus dem gemeinsamen Katalog, nach Impact sortiert. Melden Sie sich an, um Quellen stummzuschalten und Ihr Briefing zu personalisieren.",
    ),
    "Important articles and story threads from the shared catalog (%(counter)s feeds), ranked by impact. Sign in to mute sources and personalize your brief.": (
        "Articles et fils importants du catalogue partagé (%(counter)s flux), classés par impact. Connectez-vous pour couper des sources et personnaliser votre brief.",
        "Wichtige Artikel und Story-Threads aus dem gemeinsamen Katalog (%(counter)s Feeds), nach Impact sortiert. Melden Sie sich an, um Quellen stummzuschalten und Ihr Briefing zu personalisieren.",
    ),
    "New since your last visit": (
        "Nouveau depuis votre dernière visite",
        "Neu seit Ihrem letzten Besuch",
    ),
    "Earlier": ("Plus tôt", "Früher"),
    "Daily brief": ("Brief du jour", "Tägliches Briefing"),
    "Today’s brief": ("Brief du jour", "Heutiges Briefing"),
    "You’re all caught up — this brief stays fresh for about six hours.": (
        "Vous êtes à jour — ce brief reste frais environ six heures.",
        "Sie sind auf dem Stand — dieses Briefing bleibt etwa sechs Stunden frisch.",
    ),
    "You’re all caught up — this brief stays fresh for about six hours across %(counter)s feeds.": (
        "Vous êtes à jour — ce brief reste frais environ six heures sur %(counter)s flux.",
        "Sie sind auf dem Stand — dieses Briefing bleibt etwa sechs Stunden frisch über %(counter)s Feeds.",
    ),
    "Personalizing your brief… Showing top stories meanwhile.": (
        "Personnalisation de votre brief… Affichage des top histoires en attendant.",
        "Briefing wird personalisiert… Zeige derweil Top-Stories.",
    ),
    "Personalizing your brief from %(counter)s feeds… Showing top stories meanwhile.": (
        "Personnalisation de votre brief à partir de %(counter)s flux… Affichage des top histoires en attendant.",
        "Briefing aus %(counter)s Feeds wird personalisiert… Zeige derweil Top-Stories.",
    ),
    "Personalization hit a snag; showing the best available stories.": (
        "La personnalisation a échoué ; affichage des meilleures histoires disponibles.",
        "Personalisierung stockte; zeige die besten verfügbaren Stories.",
    ),
    "Your personalized reading list.": (
        "Votre liste de lecture personnalisée.",
        "Ihre personalisierte Leseliste.",
    ),
    "Your personalized reading list (%(counter)s feeds).": (
        "Votre liste de lecture personnalisée (%(counter)s flux).",
        "Ihre personalisierte Leseliste (%(counter)s Feeds).",
    ),
    "Personalizing…": ("Personnalisation…", "Personalisierung…"),
    "Pulling preferences and ranking what is worth your time.": (
        "Récupération des préférences et classement de ce qui mérite votre temps.",
        "Präferenzen laden und ranken, was Ihre Zeit wert ist.",
    ),
    "You’re all caught up. Check back later for a fresh brief.": (
        "Vous êtes à jour. Revenez plus tard pour un brief frais.",
        "Sie sind auf dem Stand. Später wiederkommen für ein frisches Briefing.",
    ),
    "All catalog feeds are muted. Re-enable some in Settings to fill your brief.": (
        "Tous les flux catalogue sont coupés. Réactivez-en dans Paramètres pour remplir votre brief.",
        "Alle Katalog-Feeds sind stumm. Reaktivieren Sie welche in den Einstellungen.",
    ),
    "Nothing left to review — either you’ve judged today’s items or scores fell below the bar.": (
        "Plus rien à revoir — vous avez jugé les éléments du jour ou les scores sont trop bas.",
        "Nichts mehr zu prüfen — Sie haben die heutigen Einträge bewertet oder die Scores liegen unter der Schwelle.",
    ),
    "Story thread": ("Fil d’actualité", "Story-Thread"),
    "Back to Stories": ("Retour aux Stories", "Zurück zu Stories"),
    "Untitled thread": ("Fil sans titre", "Unbenannter Thread"),
    "No articles in this thread yet.": (
        "Pas encore d’articles dans ce fil.",
        "Noch keine Artikel in diesem Thread.",
    ),
    "Ask about this news": (
        "Poser une question sur cette actualité",
        "Zu diesen Nachrichten fragen",
    ),
    "Ask about this %(chat_scope_label)s": (
        "Poser une question sur %(chat_scope_label)s",
        "Zu %(chat_scope_label)s fragen",
    ),
    "Follow-ups grounded in the articles on this page.": (
        "Suites ancrées dans les articles de cette page.",
        "Follow-ups auf Basis der Artikel auf dieser Seite.",
    ),
    "Ask what’s going on, how stories connect, or what the coverage emphasizes.": (
        "Demandez ce qui se passe, comment les histoires se relient, ou ce que la couverture souligne.",
        "Fragen Sie, was passiert, wie Stories zusammenhängen, oder was die Berichterstattung betont.",
    ),
    "Your question": ("Votre question", "Ihre Frage"),
    "Ask a question…": ("Posez une question…", "Frage stellen…"),
    "Send message": ("Envoyer le message", "Nachricht senden"),
    "Send": ("Envoyer", "Senden"),
    "Sign in to ask follow-up questions about this story.": (
        "Connectez-vous pour poser des questions de suivi sur cette histoire.",
        "Melden Sie sich an, um Folgefragen zu dieser Story zu stellen.",
    ),
    "Sign in with Google": ("Se connecter avec Google", "Mit Google anmelden"),
}


def _write_catalog(lang: str, index: int) -> None:
    po = polib.POFile()
    po.metadata = {
        "Project-Id-Version": "noise-to-signal",
        "Language": lang,
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Plural-Forms": "nplurals=2; plural=(n != 1);",
    }
    for msgid, pair in TRANSLATIONS.items():
        entry = polib.POEntry(msgid=msgid, msgstr=pair[index])
        po.append(entry)
    dest = LOCALE / lang / "LC_MESSAGES"
    dest.mkdir(parents=True, exist_ok=True)
    po_path = dest / "django.po"
    mo_path = dest / "django.mo"
    po.save(str(po_path))
    po.save_as_mofile(str(mo_path))
    print(f"wrote {po_path.relative_to(ROOT)} and {mo_path.name}")


def main() -> None:
    _write_catalog("fr", 0)
    _write_catalog("de", 1)


if __name__ == "__main__":
    main()
