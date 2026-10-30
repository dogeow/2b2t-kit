package dev.twob2tkit.runtime.engine;

/** Borrow only an inactive module. A newer user choice yields ownership. */
final class BorrowedPacketSneak {
    interface Access {
        boolean active() throws Exception; Object mode() throws Exception; Object packet();
        void mode(Object value) throws Exception; void active(boolean value) throws Exception;
        boolean eligible() throws Exception;
    }
    private Access access;private Object original,packet;private boolean owned,yielded;
    boolean owned(){return owned;}
    boolean update(boolean wanted,Access candidate)throws Exception{
        if(!wanted){close();yielded=false;return false;}
        if(owned){
            if(!access.active()||!packet.equals(access.mode())){owned=false;yielded=true;return candidate.eligible();}
            return access.eligible();
        }
        if(candidate.active()||yielded)return candidate.eligible();
        access=candidate;original=candidate.mode();packet=candidate.packet();
        candidate.mode(packet);
        try{candidate.active(true);owned=true;}
        catch(Exception failure){try{if(candidate.active())candidate.active(false);}finally{if(packet.equals(candidate.mode()))candidate.mode(original);}throw failure;}
        if(!candidate.eligible()){close();yielded=true;return false;}
        return true;
    }
    void close()throws Exception{
        if(owned){
            if(access.active()&&packet.equals(access.mode())){access.active(false);if(packet.equals(access.mode()))access.mode(original);}
            owned=false;
        }
    }
}
