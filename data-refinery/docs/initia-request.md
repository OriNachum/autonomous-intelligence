Create a data refinery script.
For now it should work on a data source.
It will split the documents to the most important entities and relationships in each document.
Entities include names, concepts, features, locations.
Relationships bridge between entities and help understand the connection of them.

To process big documents, we will use 3-page sliding window, and a multimodal model using vllm.
To hold all relationships use json files in an output folder.
The json files should be file per document per sliding window first page index. 
A lot of json files are easy to process, but 1 big file is hard.

We will generate from that json file a cipher instructions to build neo4j local db.

That way we refine the documents into small parts of entities and relationships, in a way that will let us rebuild new, refined, concentrated documents of data.
