# Projet MongoDB scraper pour SEO
Ce projet est constitué de 3 programmes:
- `reset.py` supprime la base de données et recrée les indexes dans les 3
collections.
- `add_url.py` ajoute la première URL dans la collection URL avec toutes les
informations nécessaires, telles que le scope, date et status.
- `scrap.py` lance un scraper.


## Architecture de la base de données
La base de données MongoDB est appelée `seo` et est consitutée de 3 collections:
`urls`, `docs` et `logs`.

### Collection `logs`
Les documents de cette collection n'ont que 2 champs obligatoires :
- `date` indiquant la date de l'événement
- `msg` indiquant la description textuelle de l'événement

D'autres champs peuvent être ajoutés en fonction de la nature de l'événement.
Notamment l'URL concernée, la page HTML récupérée ou autre informations pouvant
aider au débugage.

### Collection `urls`
La collection `urls` contient les URLs à scraper ou pas encore scrapées. La
structure des documents stockés dans la collection sont comme suit.
```
{
        "url": "http://books.toscrape.com/index.html",
        "scope": "http://books.toscrape.com/",
        "status": "pending",
        "added_at": ISODate("2024-01-12T23:06:13.322Z"),
        "started_at": null
}

```

Les champs ont la signification suivante.
- `url` indique l'URL en question.
- `scope` le préfixe d'URL d'où il ne faut pas sortir.
- `status` peut être `pending`, `inprogress`, `done` pour le fonctionnement
normal. Il peut aussi être `retry_later` ou `failed` en cas d'erreur.
- `started_at` indique la date du début du scraping, ou `null`.
- `retry_at` est optionnel et indique la date à laquelle re-tenter de récupérer
cette URL en cas d'erreur.
- `retry_count` est optionnel et indique le nombre de tentatives en cas
d'erreur.

### Collection `docs`
La collection `docs` stocke les pages web récupérées.
```
{
    "url": "http://books.toscrape.com/index.html",
    scope: "http://books.toscrape.com/",
    "html": "<html>...</html>",
    fetched_at: ISODate("2024-01-12T23:06:14.629Z"),
    title: "All products | Books to Scrape - Sandbox",
    emphasis: {
        strong: ["1000", "1", "20", "Warning!"],
        b: [],
        em: [],
        h1: ["All products"],
        h2: [],
        h3: ["A Light in the ...", "Tipping the Velvet"]
    }
}
```

Les champs `url` et `scope` ont la même signification qu'avec la collection
`urls`. Les autres sont expliqués ci-dessous.
- `html` contient tout le code HTML de la page.
- `fetched_at` contient la date de récupération de la page.
- `title` et `emphasis` contiennent des informations extraites de la page.


## Fonctionnemement normal
Dans le fonctionnement normal, le programme `add_url.py` ajoute une première URL
à la collection `urls`. Celle-ci est ensuite récupérée par un programme
`scrap.py` qui la marque comme `inprogress`.

La page est ensuite récupérée. Les liens de la page sont extraits. S'ils ne
sortent pas du `scope` (c'est à dire, si l'URL de la page pointée commence bien
par le scope) celle-ci est ajoutée à la collection `urls` si elle n'y figure pas
déjà.

La page HTML est ensuite ajoutée à la collection `docs` avec les informations
qui en ont été extraites.

Suite à cela, l'URL est marquée avec un `status` à `done`. Puis le programme
retourne récupérer une URL avec un `status` `pending`.

## Gestion des erreurs serveur
Si le serveur renvoie une erreur (erreur 500 par exemple), la page est marquée
avec un `status` `retry_later` avec un nouveau champ `retry_at` situé 10 minutes
plus tard et un champ `retry_count` à 1. Si la récupération de cette URL avait
déjà résulté en une erreur, le `retry_count` est simplement incrémenté.

Si le champ `retry_count` atteint 10, alors son `status` est passé à `failed`.

Cela signifie que le programme principal doit non seulement récupérer les URL
avec un `status` `pending` mais aussi celles avec un `status` `retry_later` et
qui ont un champ `retry_at` indiquant une date passée.

Cela signifie aussi que le scraping ne doit pas nécessairement s'arrêter s'il
n'y a rien à faire *maintenant*. S'il n'y a rien à faire *maintenant* mais
qu'une URL est marquée *retry_later* avec une date dans le future, il faut
possiblement attendre sans rien faire. Le scraping n'est réellement fini que
s'il n'y a plus aucune URL `pending` ou `retry_later`.

## Gestion des plantages de scraper
Un scraper peut planter à tout moment et laisser une URL dans un état `pending`
indéfiniment. Pour éviter cela, la boucle principale du scraper récupère
également les URL avec un `status` `inprogress` et un `started_at` vieux de plus
de 10 minutes.

Cela signifie que la boucle principale du scraper ne se termine pas non plus
s'il reste au moins une URL `inprogress`. Car le scraper en charge de celle-ci
peut avoir planté.

## Limite à 100 documents
De manière à ne pas télécharger trop de pages web (si jamais elles sont générées
avec des URL distinctes), il y a une limite fixe à 100 pages téléchargées par
scope.

Pour implémenter cette limite, dans la boucle principale, une fois qu'une URL a
été récupérée depuis la collection `urls`, le nombre de documents de la
collection `docs` est testé. S'il y a suffisamment de documents dans la
collection `docs`, cette URL fraîchement récupérée est marquée avec un `status`
`ignored`. Ceci se produira en boucle pour toutes les URLs encore non-traitée.

Étant donné que le test est effectué avant de récupérer la page web, il se peut
que plusieurs scrapers récupèrent une page pendant que le nombre de documents
est égal à 99, puis qu'ils l'insèrent tous à la fois. Tenter de limiter la
collection `docs` à exactement 100 documents par scope n'a pas été jugé
nécessaire.

## Gestion des race conditions
Partout dans le code où il y a un test puis modification de la base de donnée,
il y a potentiellement une *race condition*. Les *race conditions* ont été
gérées à plusieurs endroits du code par l'usage de `find_one_and_update` et de
l'opérateur `$setOnInsert` pour la méthode `insert_one`.
