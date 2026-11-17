# Pilotage d'opération MDB

Checklist intelligente qui couvre une opération de marchand de biens de la prospection à la clôture :
135 tâches, 9 catégories (A à I), 20 typologies, 8 jalons, dépendances, alertes et planning calculé.

## Fichiers
| Fichier | Rôle |
|---|---|
| `referentiel.json` | **Source unique.** Typologies, catégories, jalons, tâches. Toute évolution se fait ici. |
| `app.html` | Gabarit de l'application (interface et moteur). |
| `build.py` | Valide le référentiel (ID, dépendances, cycles, typologies) puis génère `index.html` et `export/*.csv`. |
| `index.html` | Application générée, autonome : s'ouvre par double-clic ou via `/pilotage` sur le serveur. |
| `export/taches.csv` | Base de tâches pour Notion ou Airtable. |
| `export/typologies.csv`, `export/jalons.csv` | Tables de référence liées. |

Après toute modification du référentiel :
```bash
python pilotage/build.py
```
```bash
python -m pytest -q tests/test_pilotage.py
```

## Logique du moteur
- **Activation par typologie** : une tâche sans typologie s'applique à toutes les opérations ; sinon elle est
  active si au moins une de ses typologies est cochée. Les alias (`@TRAVAUX`, `@URBA`, `@FONCIER`, `@LOTS`, `@NEUF`)
  regroupent plusieurs typologies.
- **Dépendances transitives** : si un prérequis est désactivé par la typologie, la tâche hérite de ses propres
  prérequis. La chaîne reste juste quel que soit le montage.
- **Chronologie automatique** : début au plus tôt = fin (réelle, sinon cible) du dernier prérequis ; date cible =
  début + durée type. Une date cible saisie à la main prime et décale les tâches suivantes.
- **Alertes** : tâche bloquée, date cible dépassée (critique si la tâche est critique), échéance critique à 7 jours,
  tâche avancée alors qu'un prérequis n'est pas terminé, tâche critique terminée sans validation finale.
- **Jalons** : J1 promesse (B08), J2 fin des CS (B17), J3 acte (B19), J4 autorisations purgées (C16),
  J5 commercialisation (G11), J6 premières ventes (H05), J7 remboursement (I03), J8 clôture (I08).

## Ajouter une typologie ou une tâche
1. Ajouter la typologie dans `typologies` (code, nom, groupe). Pour un nouveau groupe, l'ajouter dans `groupes_typologies`
   avec `"choix": "unique"` ou `"multiple"`.
2. Ajouter les tâches qui lui sont propres avec `"typo": ["NOUVEAU_CODE"]`, ou ajouter le code à un alias existant.
3. Lancer `build.py` : il refuse un ID en double, une dépendance inconnue, une typologie inconnue ou un cycle.

Les tâches propres à une seule opération s'ajoutent directement dans l'application (Paramétrage → Ajouter une tâche).

Champs d'une tâche : `id`, `cat`, `sc` (sous-catégorie), `nom`, `desc`, `resp` (liste), `decl` (déclenchement),
`dep` (liste d'ID), `crit` (Critique / Important / Confort), `risque`, `docs` (liste), `typo` (liste), `duree` (jours),
`conseil` (pratique terrain, facultatif), `verif` (`true` si la règle citée doit être confirmée par un professionnel).

## Import Notion
1. Importer `export/taches.csv` (Paramètres → Importer → CSV) : une base de données est créée.
2. Convertir les colonnes : `Statut` en *Statut* (À faire, En cours, Bloqué, En validation, Terminé) ;
   `Catégorie`, `Sous-catégorie`, `Criticité` en *Sélection* ; `Responsable`, `Typologies`, `Documents` en *Sélection multiple* ;
   `Date cible`, `Date réelle` en *Date* ; `Validation finale` et `À vérifier` en *Case à cocher*.
3. `Dépendances` : créer une relation de la base vers elle-même (« Prérequis »), puis la renseigner à partir de la colonne texte.
4. Formules utiles :
   - Retard : `and(prop("Statut") != "Terminé", not empty(prop("Date cible")), prop("Date cible") < now())`
   - Alerte critique : `and(prop("Criticité") == "Critique", prop("Retard"))`
5. Vues : Tableau groupé par Catégorie ; Kanban par Statut ; Chronologie sur Date cible ; filtre par Typologies.
   Pour plusieurs opérations, ajouter une relation « Opération » et dupliquer la base par opération ou filtrer.

## Import Airtable
1. Créer une base, importer `taches.csv`, puis `typologies.csv` et `jalons.csv` dans deux autres tables.
2. Types : `Statut`, `Criticité`, `Catégorie` en *Single select* ; `Responsable`, `Documents` en *Multiple select* ;
   `Typologies` en *Link to Typologies* ; `Dépendances` en *Link to Tâches* (même table) ; dates en *Date* ; validation en *Checkbox*.
3. Formules :
   - Retard : `AND({Statut} != "Terminé", {Date cible}, IS_BEFORE({Date cible}, TODAY()))`
   - Prérequis non terminés (rollup sur Dépendances, champ Statut) : `ARRAYJOIN(values)` puis
     `IF(FIND("À faire", {Statuts prérequis}) + FIND("En cours", {Statuts prérequis}) + FIND("Bloqué", {Statuts prérequis}), "Attend", "Prête")`
4. Interfaces : tableau de bord avec les jalons (filtre `Jalon` non vide) et les alertes (Retard ou Statut = Bloqué).

## Données et limites
- L'application enregistre les opérations dans le navigateur (stockage local). Exporter régulièrement la sauvegarde JSON
  (Paramétrage → Export) pour la conserver ou la transférer ; l'import la restaure.
- Les références légales et délais sont ceux connus à la date du référentiel. Les tâches marquées « à vérifier » portent sur
  des règles susceptibles d'évoluer (lois de finances, TVA immobilière, droits des locataires) et doivent être confirmées
  par le notaire, l'avocat ou l'expert-comptable de l'opération.
