# Mise à jour quotidienne depuis le Drive MS PROJETS

Procédure suivie chaque matin par la tâche planifiée. Elle met à jour l'application publiée
(https://claude.ai/artifact/69EmpwzayNY4brvvTvY8h6) à partir du Drive, sans rien écrire dans le Drive
ni dans ce dépôt. **Les données des opérations ne sont jamais commitées.**

## Sources
- Drive partagé **MS PROJETS** (`0ALbD98QhthRIUk9PVA`), dossier **02 - Projets MdB** (`1u56SgHPNJDvcbgt7yXCUy1UtuCllk-2i`).
- Étapes (un dossier par étape, un sous-dossier par opération) :

| Étape | ID dossier |
|---|---|
| 02 - OFFRE ENVOYEE | `1_C3X4ymrqfOdBChAuMiO-dKSoQqnMpN5` |
| 02B - OFFRE ACCEPTEE | `1GbjvdkFFEkDe-cfr_R5rchETtT3HrnF2` |
| 03 - PV SIGNEE | `1ILzsuekNkWcwF2b2aOmb9sgE6p8X0zzY` |
| 04 - AAE SIGNEE | `1BiwN9bhKvbas04CIt1iyJ2fv4SKu5ndW` |
| 05 - ACHEVES | `1Z5oAZVo1-MJimJSnzirzHty3CC-wPb1l` |
| 06 - OUT | `1cYFvtLPdw63LETeOd0Fk9nSipBQ-gPtc` |

- Journal d'opération : fichier `_HISTORIQUE_*.xlsx` dans le sous-dossier « Y - Correspondance & Historique »
  de chaque opération (mis à jour chaque nuit vers 5 h, heure de Paris).

## Étapes
1. `Artifact` action `read` sur l'URL ci-dessus ; enregistrer la page, puis
   `python pilotage/sync.py extraire <page> ops.json` (état de la veille).
2. Lister les sous-dossiers de chaque étape (Drive `search_files`, `parentId = '<id étape>'`,
   `mimeType = 'application/vnd.google-apps.folder'`) et écrire `pipeline.json` :
   `[{"dossier": "<id>", "nom": "<titre du dossier>", "etape": "<étape>"}]` (étapes 02 à 06).
3. `python pilotage/sync.py appliquer ops.json pipeline.json ops_maj.json` : crée les nouvelles opérations
   (à partir de 02 - OFFRE ENVOYEE) avec les statuts que leur étape implique, met à jour les étapes,
   marque abandonnées celles passées en 06 - OUT.
4. Pour chaque opération des étapes 02 à 04 dont le journal `_HISTORIQUE` a été modifié depuis la dernière
   mise à jour (champ `maj` de l'opération) : lire le journal (`read_file_content`) et mettre à jour dans
   `ops_maj.json` les statuts, dates réelles, dates cibles et commentaires des tâches concernées.
   - Statut seulement s'il est établi par le journal ; sinon commentaire « à vérifier ».
   - Citer la source dans le commentaire (« journal »), dates au format JJ/MM/AAAA.
   - Personnes privées (acquéreurs, vendeurs, locataires) en initiales ; professionnels par leur structure.
   - « Validation finale » seulement si la pièce elle-même est dans le Drive.
   - Points d'attention « Haute » du journal : tâche spécifique (`custom`, `"drive": true`) avec date cible.
   - Mettre `"maj"` à la date du jour pour chaque opération modifiée (sinon le navigateur ignore la mise à jour).
   - Une nouvelle opération sans journal garde la tâche X90 « Compléter la fiche de l'opération ».
5. `python pilotage/build.py --operation ops_maj.json --sortie <page>` puis `Artifact` publish de ce fichier
   avec `url` = l'URL ci-dessus.
6. Compte rendu final (3 à 8 lignes) : opérations créées, changements d'étape, nouvelles alertes critiques,
   échéances des 7 prochains jours.

## Ce que fait le navigateur
- Opération nouvelle : ajoutée.
- Opération connue avec `maj` plus récent : étape, typologies et tâches mises à jour, **sauf** les tâches
  modifiées à la main (marquées `manuel`) et les typologies retouchées à la main.
- Rien n'est supprimé côté navigateur ; une opération passée en 06 - OUT apparaît comme abandonnée.
