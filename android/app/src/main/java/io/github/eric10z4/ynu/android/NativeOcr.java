package io.github.eric10z4.ynu.android;

import android.content.Context;
import android.graphics.*;
import ai.onnxruntime.*;
import org.json.JSONArray;
import java.io.*;
import java.nio.FloatBuffer;
import java.util.Collections;

public final class NativeOcr {
    private final Context context;
    private OrtSession session;
    private JSONArray charset;
    public NativeOcr(Context context) { this.context = context.getApplicationContext(); }
    private void initialize() throws Exception {
        if (session != null) return;
        File model = new File(context.getFilesDir(), "ocr_model.onnx");
        if (!model.exists()) {
            try (InputStream in = context.getAssets().open("ocr_model.onnx"); OutputStream out = new FileOutputStream(model)) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
            }
        }
        try (InputStream in = context.getAssets().open("ocr_charset.json")) {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192]; int count;
            while ((count = in.read(buffer)) != -1) bytes.write(buffer, 0, count);
            charset = new JSONArray(bytes.toString("UTF-8"));
        }
        try (OrtSession.SessionOptions options = new OrtSession.SessionOptions()) {
            options.setIntraOpNumThreads(1);
            options.setInterOpNumThreads(1);
            session = OrtEnvironment.getEnvironment().createSession(model.getAbsolutePath(), options);
        }
    }
    public synchronized String classify(byte[] image) throws Exception {
        initialize();
        if (image.length > 2_000_000) throw new IllegalArgumentException("验证码图片过大");
        Bitmap source = BitmapFactory.decodeByteArray(image, 0, image.length);
        if (source == null || source.getHeight() == 0) throw new IllegalArgumentException("验证码图片无效");
        int width = Math.max(1, (int)(source.getWidth() * (64.0 / source.getHeight())));
        if (width > 1024) { source.recycle(); throw new IllegalArgumentException("验证码尺寸无效"); }
        Bitmap white = Bitmap.createBitmap(source.getWidth(), source.getHeight(), Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(white); canvas.drawColor(Color.WHITE); canvas.drawBitmap(source, 0, 0, null);
        Bitmap resized = Bitmap.createScaledBitmap(white, width, 64, true);
        int[] pixels = new int[width * 64]; resized.getPixels(pixels, 0, width, 0, 0, width, 64);
        float[] input = new float[pixels.length];
        for (int i = 0; i < input.length; i++) {
            int c = pixels[i];
            input[i] = Math.round(.299 * Color.red(c) + .587 * Color.green(c) + .114 * Color.blue(c)) / 255f;
        }
        source.recycle(); if (resized != white) resized.recycle(); white.recycle();
        try (OnnxTensor tensor = OnnxTensor.createTensor(OrtEnvironment.getEnvironment(), FloatBuffer.wrap(input), new long[]{1,1,64,width});
             OrtSession.Result result = session.run(Collections.singletonMap("input1", tensor))) {
            float[][][] values = (float[][][])result.get(0).getValue();
            StringBuilder text = new StringBuilder(); int previous = -1;
            for (float[][] step : values) {
                int index = 0;
                for (int k = 1; k < step[0].length; k++) if (step[0][k] > step[0][index]) index = k;
                if (index != 0 && index != previous && index < charset.length()) text.append(charset.getString(index));
                previous = index;
            }
            return text.toString();
        }
    }
}
