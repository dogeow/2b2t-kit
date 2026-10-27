package dev.twob2tkit.chat.core;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class TranslationClicksTest {
 @Test void aTokenContainsNoChatTextAndCannotCrossConnections() {
  var registry=new TranslationClicks<String>(4);Object connection=new Object();String token=registry.register("private message",connection);
  assertTrue(TranslationClicks.isToken(token));assertFalse(token.contains("private message"));
  assertNull(registry.claim(token,new Object()));assertEquals("private message",registry.claim(token,connection).value());
 }
 @Test void doubleClickCannotStartAnotherRequest() {
  var registry=new TranslationClicks<Object>(4);Object connection=new Object();String token=registry.register(new Object(),connection);
  var first=registry.claim(token,connection);assertNotNull(first);assertNull(registry.claim(token,connection));
  assertTrue(registry.finish(first));assertNotNull(registry.claim(token,connection));
 }
 @Test void canceledOldCallbackCannotFinishNewClick() {
  var registry=new TranslationClicks<Object>(4);Object connection=new Object();String token=registry.register(new Object(),connection);
  var old=registry.claim(token,connection);registry.cancelPending();var fresh=registry.claim(token,connection);
  assertFalse(registry.finish(old));assertNull(registry.claim(token,connection));assertTrue(registry.finish(fresh));
 }
 @Test void evictedOrClearedMessagesCannotBeRevived() {
  var registry=new TranslationClicks<Object>(1);Object connection=new Object();String first=registry.register(new Object(),connection);
  var old=registry.claim(first,connection);registry.register(new Object(),connection);
  assertNull(registry.get(first,connection));assertFalse(registry.finish(old));registry.clear();assertTrue(registry.values().isEmpty());
 }
 @Test void unrelatedLinksAndForgedTokensNeverResolveToMessage() {
  var registry=new TranslationClicks<Object>(4);Object connection=new Object();
  assertFalse(TranslationClicks.isToken("https://example.com"));assertFalse(TranslationClicks.isToken("/help"));
  assertNull(registry.claim(TranslationClicks.PREFIX+"forged",connection));
 }
}
