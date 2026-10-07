from __future__ import annotations


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Common words, plus words that appear in almost every Steam review.
STOPWORDS = _words(
    """
    и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
    только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли
    если уже или ни быть был была были него до вас нибудь опять уж вам ведь там
    потом себя ничего ей может они тут где есть надо ней для мы тебя их чем сам
    чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого
    какой совсем ним здесь этом один почти мой тем чтобы нее сейчас куда зачем всех
    никогда можно при наконец два об другой хоть после над больше тот через эти нас
    про всего них какая много разве эту три моя хорошо свою этой перед иногда лучше
    чуть том нельзя такой им более всегда конечно всю между это эта эти этот этих
    этому этой эту просто очень уже свою свои свой своя мое мои твои твой твоя наш
    наша наше ваши ваш ваша кто чтоб чтобы этот эта эти этом этой этого эту них ним
    нее нему меня мной тобой собой чем либо нибудь кое кто то это вот ещё еще
    the a an and or of to in on for with at by from is are was were be been being
    it this that these those i you he she we they me my your our their not no yes
    do did does doing have has had having but if so than then too very just about
    into over after before up down out off as what which who whom when where why
    how all any some can will would should could there here also only own same
    other such its im ive dont doesnt didnt cant wont isnt arent wasnt werent
    youre theyre thats theres her his him them our ours yours theirs because
    while during within without across per via than once again really much more
    most less least ever never always something anything nothing everything
    someone anyone get got getting gonna wanna lot lots bit one two three
    игра игры игре игру игрой играх game games steam
    """
)
