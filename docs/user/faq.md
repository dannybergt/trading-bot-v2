# FAQ

## Allgemein

- Warum ist nur ein Frontend-Bundle vorhanden?
  Das Frontend wurde aus dem Docker-Image extrahiert. Darin liegt nur das ausgelieferte Build, nicht zwingend der React-Quellcode.
- Sind meine Trading-Zugangsdaten sicher gespeichert?
  Noch nicht auf einem angemessenen Sicherheitsniveau. Im aktuellen Stand werden Alpaca-Zugangsdaten serverseitig im Datenbestand abgelegt und muessen vor produktivem Einsatz besser abgesichert werden.
- Ist das Tool produktionsreif?
  Nein. Es hat interessante Fachlogik, aber mehrere Sicherheits-, Betriebs- und Architekturdefizite.
- Warum kann das Projekt noch nicht sauber auf Docker Hub zurueckpubliziert werden?
  Weil der lokale Projektname und die getrennten Docker-Hub-Repositories noch nicht mit den globalen Publish-Regeln zusammenpassen.
- Wie melde ich mich als erster Admin an?
  Der Login verwendet E-Mail plus Passwort. Fuer den Erstaufbau setzt der Betreiber `INITIAL_ADMIN_EMAIL` und `INITIAL_ADMIN_PASSWORD`; dieses Bootstrap-Konto kann bei `INITIAL_ADMIN_MFA_ENABLED=false` zuerst ohne MFA anmelden und weitere Nutzer verwalten.
