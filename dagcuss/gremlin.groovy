def has_ancestor_any(needles) {
    needles = needle_ids.collect {g.v(it)}
    return (g.v(id).as('get_parents').inE.filter{it.label == 'reply'}.outV.
    loop('get_parents'){!needles.contains(it.object)}
    {needles.contains(it.object)}).toList() as Set
}
