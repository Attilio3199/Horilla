# Audit iniziale migrazione da installazione personalizzata a Horilla 2.0

Questo branch parte dal `main` personalizzato e usa Horilla 2.0 come
destinazione della migrazione. Non contiene né sostituisce l'installazione
attuale: serve a catalogare e portare le personalizzazioni in modo selettivo
e verificabile.

## Perimetro rilevato

Nella storia del repository corrente sono stati trovati 72 commit locali,
realizzati tra il 16 febbraio e il 20 luglio 2026 con gli autori
`secondary`, `Attilio3199` e `Riparazioni2`.

- 158 file distinti coinvolti;
- circa 29.597 righe aggiunte e 9.502 rimosse nei commit locali;
- 80 file di interfaccia o template;
- 69 file di logica applicativa o dati;
- 8 file di infrastruttura;
- 1 catalogo di traduzioni.

I conteggi includono revisioni successive dello stesso file: sono una misura
dell'ampiezza del lavoro, non una patch pronta da applicare direttamente.

## Personalizzazioni da migrare per prime: UI

| Area | Evidenze nella versione attuale | Strategia per 2.0 |
| --- | --- | --- |
| Stile generale | card arrotondate, `oh-card`, menu collassabile | Riprodurre con CSS/componenti 2.0, senza copiare i CSS compilati. |
| Cedolini | ricerca e pagina di controllo presenze | Ricostruire i template sul markup e sugli endpoint 2.0. |
| Dipendenti | moduli dati personali e bancari, documenti | Confrontare i context delle view 2.0 prima di portare campi o template. |
| Localizzazione | catalogo italiano aggiornato | Importare solo le stringhe ancora pertinenti, poi rigenerare i file compilati. |

## Personalizzazioni funzionali: non trattarle come UI

Queste aree vanno analizzate e migrate separatamente, perché coinvolgono
modelli, view, URL, migrazioni o dati:

- payroll: component view, URL, modelli, form e gestione controllo cedolini;
- dipendenti: campi, filtri, form, view e integrazione OpenStreetMap;
- migrazioni e vista SQL per la ripartizione oraria dei contratti;
- documenti, maternità, malattie e premi;
- Docker, PostgreSQL, Nginx, entrypoint e configurazione ambiente.

## Regole operative del branch

1. Una personalizzazione per commit, con test manuale della schermata o del
   flusso interessato.
2. Non copiare in blocco `static/build/`, migrazioni o file Docker dalla
   vecchia installazione.
3. Per ogni template, confrontare prima template, view e URL corrispondenti
   nella 2.0.
4. Le funzionalità payroll e le migrazioni SQL richiedono una prova su copia
   del database prima di qualunque rilascio.

## Prossima tranche

Partire dal tema globale e dalle pagine dei cedolini: sono il gruppo più utile
per ottenere la nuova interfaccia senza toccare subito i dati HR e payroll.
